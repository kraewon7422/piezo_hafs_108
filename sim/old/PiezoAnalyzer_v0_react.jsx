/* [repo note] v0 — first React draft of PiezoLab Analyzer (2026-05-28), kept as history only.
   Superseded by sim/PiezoAnalyzer.html (standalone) and sim/PiezoAnalyzer_v2.html.
   Not standalone: needs a React build with recharts, lucide-react and xlsx; window.storage is a chat-artifact API.
   Later chat edits were never applied to this copy. The efficiency defaults (0.80/0.90/0.82/0.95) are
   unsourced assumptions, and the synthetic 8-28 V footstep data is hypothetical, not measured.
   LTC3588 is only a rectifier + buck regulator; it does NOT do impedance matching. */
import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
} from "recharts";
import {
  Zap, Upload, Lightbulb, Save, FolderOpen, Trash2, Download, Database,
  Activity, Grid3x3, Settings, X, Plus, BarChart3, Clock, Cpu, Sparkles,
  ChevronRight, FileSpreadsheet, GitCompare, AlertTriangle, Check, Gauge,
} from "lucide-react";
import * as XLSX from "xlsx";

/* ============================================================
   압전 하베스터 데이터 분석 도구  (PiezoLab Analyzer)
   - 표준 데이터 모델 + 어댑터(import) 계층
   - 전력/에너지 계산 엔진 (V·I / V²·R / P 직접)
   - 효율 체인 → 유효 에너지
   - 시계열 / 공간 히트맵 / 전구 시뮬레이터 / 히스토리
   ============================================================ */

/* ---------- 상수 / 기본값 ---------- */
const C = {
  bg: "#0a0e14", panel: "#11161f", panel2: "#161d28", line: "#1f2937",
  text: "#e6edf3", dim: "#8b98a9", faint: "#5b6675",
  amber: "#ffb000", amber2: "#ff7a00", cyan: "#22d3ee", green: "#34d399",
  red: "#f87171", violet: "#a78bfa",
};

const DEFAULT_EFF = {
  rectifier: 0.80,   // 정류 (AC→DC, 다이오드 손실)
  storage: 0.90,     // 저장 (커패시터/배터리)
  converter: 0.82,   // DC-DC 컨버터 / LTC3588 레귤레이션
  delivery: 0.95,    // 배선/전달 손실
};

const BULB_PRESETS = [
  { name: "LED 인디케이터", w: 0.06 },
  { name: "소형 LED (1W)", w: 1.0 },
  { name: "LED 전구 (5W)", w: 5.0 },
  { name: "LED 전구 (9W)", w: 9.0 },
  { name: "백열 (40W)", w: 40.0 },
];

const TIME_UNITS = { s: 1, ms: 0.001, us: 0.000001, min: 60 };

const uid = () => Math.random().toString(36).slice(2, 10);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };

/* 에너지 단위 자동 포맷 (J 기준) */
function fmtEnergy(j) {
  if (j == null || !Number.isFinite(j)) return "—";
  const a = Math.abs(j);
  if (a >= 3600) return `${(j / 3600).toFixed(3)} Wh`;
  if (a >= 1) return `${j.toFixed(3)} J`;
  if (a >= 1e-3) return `${(j * 1e3).toFixed(2)} mJ`;
  return `${(j * 1e6).toFixed(1)} µJ`;
}
function fmtPower(w) {
  if (w == null || !Number.isFinite(w)) return "—";
  const a = Math.abs(w);
  if (a >= 1) return `${w.toFixed(3)} W`;
  if (a >= 1e-3) return `${(w * 1e3).toFixed(3)} mW`;
  if (a >= 1e-6) return `${(w * 1e6).toFixed(2)} µW`;
  return `${(w * 1e9).toFixed(1)} nW`;
}
function fmtTime(s) {
  if (s == null) return "—";
  if (s >= 3600) return `${(s / 3600).toFixed(2)} 시간`;
  if (s >= 60) return `${(s / 60).toFixed(2)} 분`;
  if (s >= 1) return `${s.toFixed(2)} 초`;
  return `${(s * 1000).toFixed(0)} ms`;
}

/* ============================================================
   계산 엔진
   dataset: { meta, tiles:[{id,x,y,label}], samples:[{tileId,t,voltage,current,power}] }
   settings: { loadR, timeUnit, eventThreshold, efficiency:{...} }
   ============================================================ */
function powerOf(s, loadR) {
  if (s.power != null) return s.power;
  if (s.voltage != null && s.current != null) return s.voltage * s.current;
  if (s.voltage != null && loadR > 0) return (s.voltage * s.voltage) / loadR;
  return 0;
}

function computeAnalysis(dataset, settings) {
  const empty = {
    ok: false, totalEnergy: 0, avgPower: 0, peakPower: 0, duration: 0,
    sampleCount: 0, activeTiles: 0, perTile: [], series: [], etaTotal: 0,
    usableEnergy: 0, usableAvgPower: 0,
  };
  if (!dataset || !dataset.samples || dataset.samples.length === 0) return empty;

  const tScale = TIME_UNITS[settings.timeUnit] ?? 1;
  const R = settings.loadR;
  const thr = settings.eventThreshold; // W, 발걸음 이벤트 판정 임계 전력

  // 표준화: 시간(초)·전력(W)
  const norm = dataset.samples.map((s) => ({
    tileId: s.tileId ?? "T?",
    t: (num(s.t) ?? 0) * tScale,
    p: powerOf(
      { voltage: num(s.voltage), current: num(s.current), power: num(s.power) },
      R
    ),
  }));

  let tMin = Infinity, tMax = -Infinity, peakPower = 0;
  for (const s of norm) {
    if (s.t < tMin) tMin = s.t;
    if (s.t > tMax) tMax = s.t;
    if (s.p > peakPower) peakPower = s.p;
  }
  const duration = Math.max(tMax - tMin, 1e-9);

  // 타일별 그룹 + 시간정렬
  const byTile = new Map();
  for (const s of norm) {
    if (!byTile.has(s.tileId)) byTile.set(s.tileId, []);
    byTile.get(s.tileId).push(s);
  }

  // 시계열 비닝 (사다리꼴 에너지를 중점 시각의 bin에 누적)
  const NB = 140;
  const binW = duration / NB;
  const binEnergy = new Float64Array(NB);

  const perTile = [];
  let totalEnergy = 0;

  for (const [tileId, arrRaw] of byTile.entries()) {
    const arr = arrRaw.sort((a, b) => a.t - b.t);
    let energy = 0, peak = 0, events = 0, prevAbove = false;
    for (let i = 0; i < arr.length; i++) {
      if (arr[i].p > peak) peak = arr[i].p;
      const above = arr[i].p >= thr && thr > 0;
      if (above && !prevAbove) events++;
      prevAbove = above;
      if (i > 0) {
        const dt = arr[i].t - arr[i - 1].t;
        if (dt > 0 && dt < duration) {
          const segE = 0.5 * (arr[i].p + arr[i - 1].p) * dt;
          energy += segE;
          const mid = (arr[i].t + arr[i - 1].t) / 2;
          let b = Math.floor((mid - tMin) / binW);
          b = clamp(b, 0, NB - 1);
          binEnergy[b] += segE;
        }
      }
    }
    totalEnergy += energy;
    const tileMeta = (dataset.tiles || []).find((t) => t.id === tileId) || {};
    perTile.push({
      tileId, label: tileMeta.label ?? tileId,
      x: tileMeta.x ?? null, y: tileMeta.y ?? null,
      energy, peak, events, count: arr.length,
    });
  }
  perTile.sort((a, b) => b.energy - a.energy);

  // 시계열 출력
  let cum = 0;
  const series = [];
  for (let i = 0; i < NB; i++) {
    cum += binEnergy[i];
    series.push({
      t: tMin + i * binW,
      power: binEnergy[i] / binW,           // 구간 평균전력 (W)
      cumEnergy: cum,                        // 누적 에너지 (J)
      cumEnergyMJ: cum * 1000,
    });
  }

  const avgPower = totalEnergy / duration;

  // 효율 체인
  const e = settings.efficiency;
  const etaTotal = e.rectifier * e.storage * e.converter * e.delivery;
  const usableEnergy = totalEnergy * etaTotal;
  const usableAvgPower = avgPower * etaTotal;

  return {
    ok: true, totalEnergy, avgPower, peakPower, duration,
    sampleCount: norm.length, activeTiles: byTile.size, perTile, series,
    tMin, tMax, etaTotal, usableEnergy, usableAvgPower,
  };
}

/* ============================================================
   합성 데이터 생성기 (하드웨어 없이 시연용)
   각 발걸음 = 타일에 감쇠 정현파 전압 트랜지언트
   ============================================================ */
function generateSynthetic(cfg) {
  const {
    cols, rows, durationSec, stepsPerMin, vPeakMin, vPeakMax,
    loadR, hotspot,
  } = cfg;
  const tiles = [];
  for (let y = 0; y < rows; y++)
    for (let x = 0; x < cols; x++)
      tiles.push({ id: `T${y * cols + x + 1}`, x, y, label: `T${y * cols + x + 1}` });

  // 핫스팟(출입구/배식대) 가중치 — 특정 타일에 통행 집중
  const centerX = hotspot ? cols * 0.5 : null;
  const weights = tiles.map((t) => {
    if (!hotspot) return 1;
    const d = Math.abs(t.x - centerX) + 0.4 * t.y;
    return Math.exp(-0.5 * d);
  });
  const wSum = weights.reduce((a, b) => a + b, 0);

  const totalSteps = Math.round((stepsPerMin * durationSec) / 60);
  const samples = [];
  const fs = 1000;        // 1 kHz 샘플링
  const span = 0.16;      // 트랜지언트 길이 0.16 s
  const tau = 0.035;      // 감쇠 시상수
  const freq = 28;        // 진동 주파수
  for (let k = 0; k < totalSteps; k++) {
    // 가중 무작위 타일 선택
    let r = Math.random() * wSum, idx = 0;
    for (let i = 0; i < weights.length; i++) { r -= weights[i]; if (r <= 0) { idx = i; break; } }
    const tile = tiles[idx];
    const t0 = Math.random() * durationSec;
    const vPeak = vPeakMin + Math.random() * (vPeakMax - vPeakMin);
    const n = Math.round(span * fs);
    for (let i = 0; i <= n; i++) {
      const tt = i / fs;
      const v = vPeak * Math.exp(-tt / tau) * Math.sin(2 * Math.PI * freq * tt);
      samples.push({ tileId: tile.id, t: +(t0 + tt).toFixed(4), voltage: +v.toFixed(4) });
    }
  }
  samples.sort((a, b) => a.t - b.t);
  return {
    meta: {
      name: `합성 데이터 ${new Date().toLocaleTimeString("ko-KR")}`,
      source: "synthetic", loadR, durationSec, steps: totalSteps,
      createdAt: Date.now(),
    },
    tiles, samples,
  };
}

/* ============================================================
   import 어댑터 — 행 배열 + 컬럼매핑 → 표준 모델
   ============================================================ */
function rowsToDataset(rows, mapping, name) {
  // rows: array of objects keyed by header
  const samples = [];
  const tileSet = new Map();
  for (const row of rows) {
    const tileId = mapping.tileId ? String(row[mapping.tileId] ?? "T1") : "T1";
    const t = mapping.t ? num(row[mapping.t]) : null;
    const voltage = mapping.voltage ? num(row[mapping.voltage]) : null;
    const current = mapping.current ? num(row[mapping.current]) : null;
    const power = mapping.power ? num(row[mapping.power]) : null;
    if (t == null && voltage == null && power == null) continue;
    samples.push({ tileId, t: t ?? 0, voltage, current, power });
    if (!tileSet.has(tileId)) {
      const x = mapping.x ? num(row[mapping.x]) : null;
      const y = mapping.y ? num(row[mapping.y]) : null;
      tileSet.set(tileId, { id: tileId, x, y, label: tileId });
    }
  }
  // 위치정보 없으면 자동 격자 배치
  const tiles = [...tileSet.values()];
  if (tiles.every((t) => t.x == null)) {
    const cols = Math.ceil(Math.sqrt(tiles.length));
    tiles.forEach((t, i) => { t.x = i % cols; t.y = Math.floor(i / cols); });
  }
  return {
    meta: { name, source: "import", createdAt: Date.now(), rowCount: samples.length },
    tiles, samples,
  };
}

/* ============================================================
   window.storage 래퍼 (없으면 메모리 폴백)
   ============================================================ */
const memStore = {};
const hasStore = () => typeof window !== "undefined" && window.storage;
async function storeList(prefix) {
  try {
    if (hasStore()) { const r = await window.storage.list(prefix); return r?.keys ?? []; }
  } catch (e) { /* fall through */ }
  return Object.keys(memStore).filter((k) => k.startsWith(prefix));
}
async function storeGet(key) {
  try {
    if (hasStore()) { const r = await window.storage.get(key); return r ? r.value : null; }
  } catch (e) { /* fall through */ }
  return memStore[key] ?? null;
}
async function storeSet(key, value) {
  try {
    if (hasStore()) { await window.storage.set(key, value); return true; }
  } catch (e) { /* fall through */ }
  memStore[key] = value; return true;
}
async function storeDel(key) {
  try { if (hasStore()) { await window.storage.delete(key); return; } } catch (e) {}
  delete memStore[key];
}

/* ============================================================
   UI 소형 컴포넌트
   ============================================================ */
const Card = ({ children, style }) => (
  <div style={{
    background: C.panel, border: `1px solid ${C.line}`, borderRadius: 12,
    padding: 16, ...style,
  }}>{children}</div>
);

function Stat({ icon: Icon, label, value, sub, accent = C.amber }) {
  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.line}`, borderRadius: 12,
      padding: "14px 16px", position: "relative", overflow: "hidden",
    }}>
      <div style={{ position: "absolute", top: 0, left: 0, width: 3, height: "100%", background: accent }} />
      <div style={{ display: "flex", alignItems: "center", gap: 7, color: C.dim, fontSize: 11, letterSpacing: 0.5, textTransform: "uppercase", fontFamily: "var(--mono)" }}>
        <Icon size={13} color={accent} /> {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 6, fontFamily: "var(--mono)", color: C.text, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: C.faint, marginTop: 3, fontFamily: "var(--mono)" }}>{sub}</div>}
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, fmt }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.dim, marginBottom: 5, fontFamily: "var(--mono)" }}>
        <span>{label}</span><span style={{ color: C.amber }}>{fmt ? fmt(value) : value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: C.amber }} />
    </div>
  );
}

function Tab({ active, onClick, icon: Icon, children }) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 7, padding: "9px 14px",
      background: active ? C.panel2 : "transparent",
      border: `1px solid ${active ? C.amber : "transparent"}`,
      borderRadius: 9, color: active ? C.text : C.dim, cursor: "pointer",
      fontSize: 13, fontFamily: "var(--mono)", fontWeight: active ? 600 : 400,
      transition: "all .15s",
    }}>
      <Icon size={15} color={active ? C.amber : C.dim} />{children}
    </button>
  );
}

const Btn = ({ children, onClick, icon: Icon, kind = "ghost", disabled, style }) => {
  const styles = {
    primary: { background: C.amber, color: "#1a1300", border: "none" },
    ghost: { background: C.panel2, color: C.text, border: `1px solid ${C.line}` },
    danger: { background: "transparent", color: C.red, border: `1px solid ${C.red}44` },
  };
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 13px",
      borderRadius: 8, cursor: disabled ? "not-allowed" : "pointer", fontSize: 13,
      fontFamily: "var(--mono)", fontWeight: 600, opacity: disabled ? 0.4 : 1,
      ...styles[kind], ...style,
    }}>
      {Icon && <Icon size={15} />}{children}
    </button>
  );
};

/* 차트 툴팁 */
const TT = ({ active, payload, label, kind }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: C.bg, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 11px", fontFamily: "var(--mono)", fontSize: 12 }}>
      <div style={{ color: C.dim, marginBottom: 4 }}>t = {Number(label).toFixed(2)} s</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>
          {p.name}: {kind === "energy" ? fmtEnergy(p.value / 1000) : fmtPower(p.value)}
        </div>
      ))}
    </div>
  );
};

/* ============================================================
   메인 앱
   ============================================================ */
export default function PiezoAnalyzer() {
  const [dataset, setDataset] = useState(null);
  const [tab, setTab] = useState("data");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settings, setSettings] = useState({
    loadR: 10000, timeUnit: "s", eventThreshold: 0.0005,
    efficiency: { ...DEFAULT_EFF },
  });

  // import 워크플로 상태
  const [rawRows, setRawRows] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [importName, setImportName] = useState("");

  // 합성 설정
  const [syn, setSyn] = useState({
    cols: 6, rows: 4, durationSec: 60, stepsPerMin: 90,
    vPeakMin: 8, vPeakMax: 28, hotspot: true,
  });

  // 전구 시뮬
  const [bulbW, setBulbW] = useState(1.0);
  const [bulbMode, setBulbMode] = useState("continuous"); // continuous | budget
  const [budgetBulbs, setBudgetBulbs] = useState(5);

  // 히스토리
  const [instances, setInstances] = useState([]);
  const [compareSel, setCompareSel] = useState([]);
  const [toast, setToast] = useState(null);
  const fileRef = useRef(null);
  const jsonRef = useRef(null);

  const A = useMemo(() => computeAnalysis(dataset, settings), [dataset, settings]);

  const flash = (msg, kind = "ok") => { setToast({ msg, kind }); setTimeout(() => setToast(null), 2600); };

  /* ---- 히스토리 로드 ---- */
  const refreshInstances = useCallback(async () => {
    const keys = await storeList("pzt:inst:");
    const out = [];
    for (const k of keys) {
      const v = await storeGet(k);
      if (v) { try { const o = JSON.parse(v); out.push({ key: k, ...o.summary, name: o.name }); } catch {} }
    }
    out.sort((a, b) => (b.savedAt ?? 0) - (a.savedAt ?? 0));
    setInstances(out);
  }, []);
  useEffect(() => { refreshInstances(); }, [refreshInstances]);

  /* ---- 파일 업로드 ---- */
  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const buf = await f.arrayBuffer();
    const wb = XLSX.read(buf, { type: "array" });
    const ws = wb.Sheets[wb.SheetNames[0]];
    const rows = XLSX.utils.sheet_to_json(ws, { defval: null });
    if (!rows.length) { flash("빈 파일입니다", "err"); return; }
    const hdr = Object.keys(rows[0]);
    setRawRows(rows); setHeaders(hdr); setImportName(f.name);
    // 헤더 이름으로 자동 매핑 추측
    const guess = (...keys) => hdr.find((h) => keys.some((k) => h.toLowerCase().includes(k)));
    setMapping({
      tileId: guess("tile", "타일", "id", "sensor", "node"),
      t: guess("time", "시간", "t", "timestamp", "sec"),
      voltage: guess("volt", "전압", "v"),
      current: guess("curr", "전류", "i", "amp"),
      power: guess("power", "전력", "watt", "p"),
      x: guess("x", "col"), y: guess("y", "row"),
    });
    setTab("data");
    flash(`${rows.length}행 로드됨 — 컬럼 매핑을 확인하세요`);
  };

  const applyMapping = () => {
    if (!rawRows) return;
    const ds = rowsToDataset(rawRows, mapping, importName || "가져온 데이터");
    setDataset(ds); setRawRows(null); setTab("analysis");
    flash(`표준 모델로 변환 완료 (${ds.samples.length} 샘플)`);
  };

  const makeSynthetic = () => {
    const ds = generateSynthetic({ ...syn, loadR: settings.loadR });
    setDataset(ds); setTab("analysis");
    flash(`합성 데이터 생성: ${ds.samples.length} 샘플 / ${ds.meta.steps} 발걸음`);
  };

  /* ---- 히스토리 저장/불러오기 ---- */
  const saveInstance = async () => {
    if (!A.ok) { flash("저장할 분석이 없습니다", "err"); return; }
    const id = uid();
    const key = `pzt:inst:${id}`;
    const payload = {
      id, name: dataset.meta?.name || `분석 ${new Date().toLocaleString("ko-KR")}`,
      dataset, settings,
      summary: {
        id, savedAt: Date.now(),
        totalEnergy: A.totalEnergy, usableEnergy: A.usableEnergy,
        avgPower: A.avgPower, peakPower: A.peakPower, duration: A.duration,
        activeTiles: A.activeTiles, sampleCount: A.sampleCount, etaTotal: A.etaTotal,
      },
    };
    const str = JSON.stringify(payload);
    const sizeMB = str.length / 1e6;
    if (sizeMB > 4.6) {
      // 원본이 너무 크면 요약만 저장 (무손실 아카이브는 JSON export로 안내)
      const lite = { ...payload, dataset: null, _lite: true };
      await storeSet(key, JSON.stringify(lite));
      flash(`용량(${sizeMB.toFixed(1)}MB) 초과 → 요약만 저장. 원본은 JSON으로 내보내세요`, "warn");
    } else {
      await storeSet(key, str);
      flash("인스턴스 저장 완료");
    }
    refreshInstances();
  };

  const loadInstance = async (key) => {
    const v = await storeGet(key);
    if (!v) return;
    const o = JSON.parse(v);
    if (o._lite || !o.dataset) { flash("요약본입니다(원본 미저장). JSON 파일로 불러오세요", "warn"); return; }
    setDataset(o.dataset); setSettings(o.settings); setTab("analysis");
    flash(`불러옴: ${o.name}`);
  };

  const delInstance = async (key) => { await storeDel(key); refreshInstances(); flash("삭제됨"); };

  const exportJSON = () => {
    if (!dataset) return;
    const payload = { version: 1, dataset, settings, exportedAt: Date.now() };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(dataset.meta?.name || "piezo").replace(/\s+/g, "_")}.json`;
    a.click(); URL.revokeObjectURL(a.href);
    flash("JSON 내보내기 완료 (무손실 아카이브)");
  };

  const importJSON = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    try {
      const o = JSON.parse(await f.text());
      if (o.dataset) { setDataset(o.dataset); if (o.settings) setSettings(o.settings); setTab("analysis"); flash("JSON 불러오기 완료"); }
      else flash("형식이 올바르지 않습니다", "err");
    } catch { flash("JSON 파싱 실패", "err"); }
  };

  /* ---- 전구 시뮬 계산 ---- */
  const bulb = useMemo(() => {
    const pAvail = A.usableAvgPower;
    const nCont = bulbW > 0 ? Math.floor(pAvail / bulbW) : 0;
    const fracExtra = bulbW > 0 ? (pAvail / bulbW) - nCont : 0;
    const bulbSeconds = bulbW > 0 ? A.usableEnergy / bulbW : 0;          // 1개 켤 수 있는 시간
    const runtimeN = (budgetBulbs > 0 && bulbW > 0) ? A.usableEnergy / (budgetBulbs * bulbW) : 0;
    return { pAvail, nCont, fracExtra, bulbSeconds, runtimeN };
  }, [A, bulbW, budgetBulbs]);

  /* 일일 환산 (현재 측정창 기준 선형 외삽) */
  const perDay = A.ok ? (A.totalEnergy / A.duration) * 86400 : 0;
  const perDayUsable = perDay * A.etaTotal;

  /* ---- 효율 setter ---- */
  const setEff = (k, v) => setSettings((s) => ({ ...s, efficiency: { ...s.efficiency, [k]: v } }));

  const heatMax = useMemo(() => A.perTile.reduce((m, t) => Math.max(m, t.energy), 0) || 1, [A]);

  return (
    <div style={{ background: C.bg, color: C.text, minHeight: "100vh", fontFamily: "var(--body)", position: "relative" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        :root{ --mono:'JetBrains Mono',monospace; --body:'Bricolage Grotesque',system-ui,sans-serif; }
        *{ box-sizing:border-box; } body{ margin:0; }
        ::-webkit-scrollbar{ width:9px; height:9px; } ::-webkit-scrollbar-thumb{ background:${C.line}; border-radius:6px; }
        select,input[type=text],input[type=number]{ background:${C.panel2}; border:1px solid ${C.line}; color:${C.text}; border-radius:7px; padding:7px 9px; font-family:var(--mono); font-size:12px; outline:none; }
        select:focus,input:focus{ border-color:${C.amber}; }
        @keyframes glow{ 0%,100%{ filter:drop-shadow(0 0 3px ${C.amber}) drop-shadow(0 0 8px ${C.amber2}); } 50%{ filter:drop-shadow(0 0 6px ${C.amber}) drop-shadow(0 0 16px ${C.amber2}); } }
        @keyframes slideIn{ from{ transform:translateX(100%);} to{ transform:translateX(0);} }
      `}</style>

      {/* 헤더 */}
      <div style={{ borderBottom: `1px solid ${C.line}`, padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, background: `${C.bg}f0`, backdropFilter: "blur(8px)", zIndex: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: `linear-gradient(135deg,${C.amber},${C.amber2})`, display: "grid", placeItems: "center" }}>
            <Zap size={22} color="#1a1300" fill="#1a1300" />
          </div>
          <div>
            <div style={{ fontFamily: "var(--body)", fontWeight: 700, fontSize: 19, letterSpacing: -0.3 }}>PiezoLab Analyzer</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: C.dim }}>압전 하베스터 데이터 분석 · 유리프로</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn icon={Save} onClick={saveInstance} disabled={!A.ok}>저장</Btn>
          <Btn icon={Download} onClick={exportJSON} disabled={!dataset}>JSON</Btn>
        </div>
      </div>

      {/* 탭 */}
      <div style={{ display: "flex", gap: 8, padding: "14px 24px 0", flexWrap: "wrap" }}>
        <Tab active={tab === "data"} onClick={() => setTab("data")} icon={Database}>데이터</Tab>
        <Tab active={tab === "analysis"} onClick={() => setTab("analysis")} icon={Activity}>분석</Tab>
        <Tab active={tab === "spatial"} onClick={() => setTab("spatial")} icon={Grid3x3}>공간</Tab>
        <Tab active={tab === "settings"} onClick={() => setTab("settings")} icon={Settings}>효율·설정</Tab>
        <Tab active={tab === "history"} onClick={() => setTab("history")} icon={Clock}>히스토리</Tab>
      </div>

      <div style={{ padding: "18px 24px 80px", maxWidth: 1200, margin: "0 auto" }}>

        {/* ============ 데이터 탭 ============ */}
        {tab === "data" && (
          <div style={{ display: "grid", gap: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {/* 합성 생성기 */}
              <Card>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <Sparkles size={17} color={C.cyan} />
                  <span style={{ fontWeight: 700, fontSize: 15, fontFamily: "var(--body)" }}>합성 데이터 생성</span>
                </div>
                <p style={{ color: C.dim, fontSize: 12.5, marginTop: 0, lineHeight: 1.55 }}>
                  하드웨어가 없는 지금, 발걸음 트랜지언트를 물리적으로 모사해 모든 기능을 시연합니다.
                  실제 데이터가 오면 동일한 분석 엔진이 그대로 작동합니다.
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
                  <Slider label="타일 열(cols)" value={syn.cols} min={2} max={12} step={1} onChange={(v) => setSyn({ ...syn, cols: v })} />
                  <Slider label="타일 행(rows)" value={syn.rows} min={2} max={10} step={1} onChange={(v) => setSyn({ ...syn, rows: v })} />
                  <Slider label="측정 시간" value={syn.durationSec} min={10} max={300} step={5} onChange={(v) => setSyn({ ...syn, durationSec: v })} fmt={(v) => `${v}s`} />
                  <Slider label="분당 발걸음" value={syn.stepsPerMin} min={10} max={300} step={5} onChange={(v) => setSyn({ ...syn, stepsPerMin: v })} />
                  <Slider label="최소 첨두전압" value={syn.vPeakMin} min={1} max={30} step={1} onChange={(v) => setSyn({ ...syn, vPeakMin: v })} fmt={(v) => `${v}V`} />
                  <Slider label="최대 첨두전압" value={syn.vPeakMax} min={5} max={60} step={1} onChange={(v) => setSyn({ ...syn, vPeakMax: v })} fmt={(v) => `${v}V`} />
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: C.dim, margin: "4px 0 12px", fontFamily: "var(--mono)", cursor: "pointer" }}>
                  <input type="checkbox" checked={syn.hotspot} onChange={(e) => setSyn({ ...syn, hotspot: e.target.checked })} style={{ accentColor: C.cyan }} />
                  통행 핫스팟(출입구/배식대) 모사
                </label>
                <Btn kind="primary" icon={Sparkles} onClick={makeSynthetic} style={{ width: "100%", justifyContent: "center" }}>합성 데이터 생성하기</Btn>
              </Card>

              {/* 파일 import */}
              <Card>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <FileSpreadsheet size={17} color={C.amber} />
                  <span style={{ fontWeight: 700, fontSize: 15, fontFamily: "var(--body)" }}>실측 데이터 가져오기</span>
                </div>
                <p style={{ color: C.dim, fontSize: 12.5, marginTop: 0, lineHeight: 1.55 }}>
                  엑셀(.xlsx) · CSV를 올린 뒤, 어떤 열이 타일/시간/전압/전류/전력인지 매핑합니다.
                  하드웨어 출력 형식이 바뀌어도 매핑만 다시 하면 됩니다.
                </p>
                <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" onChange={onFile} style={{ display: "none" }} />
                <input ref={jsonRef} type="file" accept=".json" onChange={importJSON} style={{ display: "none" }} />
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Btn kind="primary" icon={Upload} onClick={() => fileRef.current?.click()}>엑셀/CSV 업로드</Btn>
                  <Btn icon={FolderOpen} onClick={() => jsonRef.current?.click()}>JSON 불러오기</Btn>
                </div>

                {rawRows && (
                  <div style={{ marginTop: 16, borderTop: `1px solid ${C.line}`, paddingTop: 14 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 10, fontFamily: "var(--mono)", color: C.cyan }}>
                      컬럼 매핑 ({rawRows.length}행 · {headers.length}열)
                    </div>
                    {[
                      ["tileId", "타일 ID *"], ["t", "시간 *"], ["voltage", "전압(V)"],
                      ["current", "전류(A)"], ["power", "전력(W)"], ["x", "X 위치"], ["y", "Y 위치"],
                    ].map(([k, lbl]) => (
                      <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
                        <span style={{ width: 80, fontSize: 11.5, color: C.dim, fontFamily: "var(--mono)" }}>{lbl}</span>
                        <select value={mapping[k] || ""} onChange={(e) => setMapping({ ...mapping, [k]: e.target.value || null })} style={{ flex: 1 }}>
                          <option value="">(없음)</option>
                          {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                        </select>
                      </div>
                    ))}
                    <Btn kind="primary" icon={Check} onClick={applyMapping} style={{ width: "100%", justifyContent: "center", marginTop: 8 }}>매핑 적용 → 분석</Btn>
                  </div>
                )}
              </Card>
            </div>

            {dataset && (
              <Card>
                <div style={{ fontSize: 13, fontFamily: "var(--mono)", color: C.dim, marginBottom: 8 }}>현재 데이터셋</div>
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontFamily: "var(--mono)", fontSize: 13 }}>
                  <span><span style={{ color: C.faint }}>이름</span> {dataset.meta?.name}</span>
                  <span><span style={{ color: C.faint }}>샘플</span> {dataset.samples.length.toLocaleString()}</span>
                  <span><span style={{ color: C.faint }}>타일</span> {dataset.tiles.length}</span>
                  <span><span style={{ color: C.faint }}>소스</span> {dataset.meta?.source}</span>
                </div>
              </Card>
            )}
          </div>
        )}

        {/* ============ 분석 탭 ============ */}
        {tab === "analysis" && (
          !A.ok ? <Empty onGo={() => setTab("data")} /> : (
            <div style={{ display: "grid", gap: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12 }}>
                <Stat icon={Database} label="총 발전 에너지" value={fmtEnergy(A.totalEnergy)} sub={`${A.duration.toFixed(1)}s 측정창`} accent={C.amber} />
                <Stat icon={Gauge} label="유효 에너지" value={fmtEnergy(A.usableEnergy)} sub={`η = ${(A.etaTotal * 100).toFixed(1)}%`} accent={C.green} />
                <Stat icon={Activity} label="평균 전력" value={fmtPower(A.avgPower)} sub={`유효 ${fmtPower(A.usableAvgPower)}`} accent={C.cyan} />
                <Stat icon={Zap} label="첨두 전력" value={fmtPower(A.peakPower)} accent={C.amber2} />
                <Stat icon={Grid3x3} label="활성 타일" value={A.activeTiles} sub={`${A.sampleCount.toLocaleString()} 샘플`} accent={C.violet} />
                <Stat icon={Clock} label="일일 환산(외삽)" value={fmtEnergy(perDay)} sub={`유효 ${fmtEnergy(perDayUsable)}`} accent={C.amber} />
              </div>

              <Card>
                <ChartTitle icon={Activity} color={C.cyan}>구간 평균 전력 (시계열)</ChartTitle>
                <ResponsiveContainer width="100%" height={230}>
                  <AreaChart data={A.series} margin={{ top: 6, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="gp" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={C.cyan} stopOpacity={0.5} />
                        <stop offset="100%" stopColor={C.cyan} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={C.line} strokeDasharray="3 3" />
                    <XAxis dataKey="t" tickFormatter={(v) => v.toFixed(0)} stroke={C.faint} tick={{ fontSize: 11, fontFamily: "var(--mono)" }} />
                    <YAxis tickFormatter={(v) => fmtPower(v).replace(/ /, "")} stroke={C.faint} tick={{ fontSize: 10, fontFamily: "var(--mono)" }} width={62} />
                    <Tooltip content={<TT kind="power" />} />
                    <Area type="monotone" dataKey="power" name="전력" stroke={C.cyan} fill="url(#gp)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </Card>

              <Card>
                <ChartTitle icon={Database} color={C.amber}>누적 에너지</ChartTitle>
                <ResponsiveContainer width="100%" height={210}>
                  <AreaChart data={A.series} margin={{ top: 6, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="ge" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={C.amber} stopOpacity={0.5} />
                        <stop offset="100%" stopColor={C.amber} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={C.line} strokeDasharray="3 3" />
                    <XAxis dataKey="t" tickFormatter={(v) => v.toFixed(0)} stroke={C.faint} tick={{ fontSize: 11, fontFamily: "var(--mono)" }} />
                    <YAxis tickFormatter={(v) => fmtEnergy(v / 1000).replace(/ /, "")} stroke={C.faint} tick={{ fontSize: 10, fontFamily: "var(--mono)" }} width={62} />
                    <Tooltip content={<TT kind="energy" />} />
                    <Area type="monotone" dataKey="cumEnergyMJ" name="누적에너지" stroke={C.amber} fill="url(#ge)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </Card>

              <Card>
                <ChartTitle icon={BarChart3} color={C.violet}>타일별 에너지 기여 (상위 12)</ChartTitle>
                <ResponsiveContainer width="100%" height={Math.max(180, Math.min(A.perTile.length, 12) * 26)}>
                  <BarChart data={A.perTile.slice(0, 12)} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke={C.line} strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(v) => fmtEnergy(v).replace(/ /, "")} stroke={C.faint} tick={{ fontSize: 10, fontFamily: "var(--mono)" }} />
                    <YAxis type="category" dataKey="label" stroke={C.faint} tick={{ fontSize: 11, fontFamily: "var(--mono)" }} width={48} />
                    <Tooltip cursor={{ fill: C.panel2 }} content={({ active, payload }) => active && payload?.length ? (
                      <div style={{ background: C.bg, border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 11px", fontFamily: "var(--mono)", fontSize: 12 }}>
                        <div style={{ color: C.text }}>{payload[0].payload.label}</div>
                        <div style={{ color: C.amber }}>에너지: {fmtEnergy(payload[0].value)}</div>
                        <div style={{ color: C.dim }}>이벤트: {payload[0].payload.events} · 샘플: {payload[0].payload.count}</div>
                      </div>
                    ) : null} />
                    <Bar dataKey="energy" radius={[0, 4, 4, 0]}>
                      {A.perTile.slice(0, 12).map((_, i) => <Cell key={i} fill={i === 0 ? C.amber : C.violet} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </div>
          )
        )}

        {/* ============ 공간 탭 ============ */}
        {tab === "spatial" && (
          !A.ok ? <Empty onGo={() => setTab("data")} /> : (
            <Card>
              <ChartTitle icon={Grid3x3} color={C.amber}>공간 에너지 히트맵</ChartTitle>
              <p style={{ color: C.dim, fontSize: 12.5, marginTop: 0 }}>
                타일 위치별 누적 에너지 분포. 색이 진할수록 발전(=통행)이 집중된 위치입니다 — 배식대·출입구 동선 분석에 직결됩니다.
              </p>
              <SpatialHeatmap perTile={A.perTile} max={heatMax} />
            </Card>
          )
        )}

        {/* ============ 효율·설정 탭 ============ */}
        {tab === "settings" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Card>
              <ChartTitle icon={Gauge} color={C.green}>효율 체인 (측정 출력 이후 손실)</ChartTitle>
              <p style={{ color: C.dim, fontSize: 12, marginTop: 0, lineHeight: 1.5 }}>
                압전 소자가 만든 전기가 전구까지 가는 동안의 손실. 각 단을 곱해 종단 효율 η을 만듭니다.
              </p>
              <Slider label="정류 (AC→DC)" value={settings.efficiency.rectifier} min={0.3} max={1} step={0.01} onChange={(v) => setEff("rectifier", v)} fmt={(v) => `${(v * 100).toFixed(0)}%`} />
              <Slider label="저장 (커패시터)" value={settings.efficiency.storage} min={0.3} max={1} step={0.01} onChange={(v) => setEff("storage", v)} fmt={(v) => `${(v * 100).toFixed(0)}%`} />
              <Slider label="DC-DC 컨버터 (LTC3588 등)" value={settings.efficiency.converter} min={0.3} max={1} step={0.01} onChange={(v) => setEff("converter", v)} fmt={(v) => `${(v * 100).toFixed(0)}%`} />
              <Slider label="전달/배선" value={settings.efficiency.delivery} min={0.5} max={1} step={0.01} onChange={(v) => setEff("delivery", v)} fmt={(v) => `${(v * 100).toFixed(0)}%`} />
              <div style={{ marginTop: 12, padding: 12, background: C.panel2, borderRadius: 9, textAlign: "center" }}>
                <div style={{ color: C.dim, fontSize: 12, fontFamily: "var(--mono)" }}>종단 효율 η_total</div>
                <div style={{ color: C.green, fontSize: 30, fontWeight: 700, fontFamily: "var(--mono)" }}>{(A.etaTotal * 100).toFixed(1)}%</div>
              </div>
            </Card>
            <Card>
              <ChartTitle icon={Cpu} color={C.cyan}>측정/계산 파라미터</ChartTitle>
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 12, color: C.dim, marginBottom: 5, fontFamily: "var(--mono)" }}>부하 저항 R (전압만 받을 때 P=V²/R)</div>
                <input type="number" value={settings.loadR} onChange={(e) => setSettings({ ...settings, loadR: num(e.target.value) || 1 })} style={{ width: "100%" }} />
              </div>
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 12, color: C.dim, marginBottom: 5, fontFamily: "var(--mono)" }}>시간 단위 (입력 데이터의 t 열)</div>
                <select value={settings.timeUnit} onChange={(e) => setSettings({ ...settings, timeUnit: e.target.value })} style={{ width: "100%" }}>
                  <option value="s">초 (s)</option><option value="ms">밀리초 (ms)</option>
                  <option value="us">마이크로초 (µs)</option><option value="min">분 (min)</option>
                </select>
              </div>
              <Slider label="이벤트(발걸음) 판정 임계전력" value={settings.eventThreshold * 1000} min={0} max={5} step={0.05} onChange={(v) => setSettings({ ...settings, eventThreshold: v / 1000 })} fmt={(v) => `${v.toFixed(2)} mW`} />
              <div style={{ marginTop: 8, padding: 11, background: C.panel2, borderRadius: 9, fontSize: 11.5, color: C.faint, fontFamily: "var(--mono)", lineHeight: 1.6 }}>
                계산 우선순위: ① 전력(P) 직접 → ② P=V·I → ③ P=V²/R<br />
                에너지: 사다리꼴 적분 ∫P dt (타일별 후 합산)
              </div>
            </Card>
          </div>
        )}

        {/* ============ 히스토리 탭 ============ */}
        {tab === "history" && (
          <div style={{ display: "grid", gap: 16 }}>
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <ChartTitle icon={Clock} color={C.amber}>저장된 분석 인스턴스</ChartTitle>
                <div style={{ display: "flex", gap: 8 }}>
                  <Btn icon={Save} onClick={saveInstance} disabled={!A.ok}>현재 저장</Btn>
                  <Btn icon={GitCompare} kind={compareSel.length === 2 ? "primary" : "ghost"} onClick={() => compareSel.length === 2 ? null : flash("비교할 인스턴스 2개를 선택하세요", "warn")}>비교 {compareSel.length}/2</Btn>
                </div>
              </div>
              {instances.length === 0 ? (
                <div style={{ color: C.faint, fontFamily: "var(--mono)", fontSize: 13, padding: "20px 0", textAlign: "center" }}>
                  저장된 인스턴스가 없습니다. 분석 후 "현재 저장"을 누르세요.
                </div>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {instances.map((it) => {
                    const sel = compareSel.includes(it.key);
                    return (
                      <div key={it.key} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 13px", background: sel ? C.panel2 : C.bg, border: `1px solid ${sel ? C.amber : C.line}`, borderRadius: 9 }}>
                        <input type="checkbox" checked={sel} onChange={() => setCompareSel((s) => sel ? s.filter((k) => k !== it.key) : [...s, it.key].slice(-2))} style={{ accentColor: C.amber }} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: 13.5, fontFamily: "var(--body)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.name}</div>
                          <div style={{ fontSize: 11, color: C.faint, fontFamily: "var(--mono)" }}>
                            {new Date(it.savedAt).toLocaleString("ko-KR")} · {fmtEnergy(it.totalEnergy)} · 유효 {fmtEnergy(it.usableEnergy)}
                          </div>
                        </div>
                        <Btn icon={FolderOpen} onClick={() => loadInstance(it.key)}>불러오기</Btn>
                        <Btn kind="danger" icon={Trash2} onClick={() => delInstance(it.key)} style={{ padding: "8px 10px" }}>{""}</Btn>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>

            {compareSel.length === 2 && <CompareView keys={compareSel} />}
          </div>
        )}
      </div>

      {/* ============ 전구 드로어 (당겨서 여는 창) ============ */}
      <div onClick={() => setDrawerOpen((o) => !o)} style={{
        position: "fixed", right: drawerOpen ? 340 : 0, top: "50%", transform: "translateY(-50%)",
        background: `linear-gradient(135deg,${C.amber},${C.amber2})`, color: "#1a1300",
        padding: "16px 9px", borderRadius: "10px 0 0 10px", cursor: "pointer", zIndex: 40,
        display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
        writingMode: "vertical-rl", fontFamily: "var(--mono)", fontWeight: 700, fontSize: 12,
        transition: "right .3s cubic-bezier(.4,0,.2,1)", boxShadow: "-4px 0 16px #0008",
      }}>
        <Lightbulb size={18} />전구 시뮬
      </div>
      <div style={{
        position: "fixed", right: 0, top: 0, height: "100vh", width: 340,
        background: C.panel, borderLeft: `1px solid ${C.line}`, zIndex: 39,
        transform: drawerOpen ? "translateX(0)" : "translateX(100%)",
        transition: "transform .3s cubic-bezier(.4,0,.2,1)", overflowY: "auto", padding: 20,
        boxShadow: "-8px 0 24px #0006",
      }}>
        <BulbPanel A={A} bulbW={bulbW} setBulbW={setBulbW} mode={bulbMode} setMode={setBulbMode}
          budgetBulbs={budgetBulbs} setBudgetBulbs={setBudgetBulbs} bulb={bulb}
          onClose={() => setDrawerOpen(false)} perDayUsable={perDayUsable} />
      </div>

      {/* 토스트 */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", zIndex: 60,
          background: C.panel, border: `1px solid ${toast.kind === "err" ? C.red : toast.kind === "warn" ? C.amber : C.green}`,
          color: C.text, padding: "11px 18px", borderRadius: 10, fontFamily: "var(--mono)", fontSize: 13,
          display: "flex", alignItems: "center", gap: 9, boxShadow: "0 8px 24px #0008",
        }}>
          {toast.kind === "err" ? <AlertTriangle size={16} color={C.red} /> : toast.kind === "warn" ? <AlertTriangle size={16} color={C.amber} /> : <Check size={16} color={C.green} />}
          {toast.msg}
        </div>
      )}
    </div>
  );
}

/* ---------- 보조 컴포넌트들 ---------- */
function ChartTitle({ icon: Icon, color, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
      <Icon size={16} color={color} />
      <span style={{ fontWeight: 700, fontSize: 14.5, fontFamily: "var(--body)" }}>{children}</span>
    </div>
  );
}

function Empty({ onGo }) {
  return (
    <div style={{ textAlign: "center", padding: "70px 20px", color: C.faint }}>
      <Database size={42} color={C.line} style={{ marginBottom: 14 }} />
      <div style={{ fontFamily: "var(--body)", fontSize: 17, color: C.dim, marginBottom: 6 }}>분석할 데이터가 없습니다</div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 12.5, marginBottom: 18 }}>합성 데이터를 생성하거나 실측 파일을 가져오세요</div>
      <Btn kind="primary" icon={Database} onClick={onGo}>데이터 탭으로</Btn>
    </div>
  );
}

function SpatialHeatmap({ perTile, max }) {
  const cells = perTile.filter((t) => t.x != null && t.y != null);
  if (!cells.length) return <div style={{ color: C.faint, fontFamily: "var(--mono)", fontSize: 13 }}>위치 정보가 없는 타일입니다.</div>;
  const cols = Math.max(...cells.map((c) => c.x)) + 1;
  const rows = Math.max(...cells.map((c) => c.y)) + 1;
  const grid = {};
  cells.forEach((c) => { grid[`${c.x},${c.y}`] = c; });
  const color = (frac) => {
    // 검정 → 보라 → 앰버 그라데이션
    const r = Math.round(255 * Math.min(1, frac * 1.4));
    const g = Math.round(176 * frac);
    const b = Math.round(80 * (1 - frac) + 40);
    return `rgb(${r},${g},${b})`;
  };
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols},1fr)`, gap: 6, maxWidth: cols * 92 }}>
        {Array.from({ length: rows * cols }).map((_, i) => {
          const x = i % cols, y = Math.floor(i / cols);
          const c = grid[`${x},${y}`];
          const frac = c ? c.energy / max : 0;
          return (
            <div key={i} title={c ? `${c.label}: ${fmtEnergy(c.energy)} · ${c.events} 이벤트` : "비활성"} style={{
              aspectRatio: "1", borderRadius: 8, background: c ? color(frac) : C.panel2,
              border: `1px solid ${C.line}`, display: "grid", placeItems: "center",
              fontFamily: "var(--mono)", fontSize: 10, color: frac > 0.5 ? "#1a1300" : C.dim,
              fontWeight: 600, position: "relative",
            }}>
              <span>{c?.label}</span>
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 16, fontFamily: "var(--mono)", fontSize: 11, color: C.dim }}>
        <span>낮음</span>
        <div style={{ flex: 1, maxWidth: 200, height: 10, borderRadius: 5, background: `linear-gradient(90deg,${color(0)},${color(0.5)},${color(1)})` }} />
        <span>높음 ({fmtEnergy(max)})</span>
      </div>
    </div>
  );
}

/* 전구 시뮬레이터 패널 */
function BulbPanel({ A, bulbW, setBulbW, mode, setMode, budgetBulbs, setBudgetBulbs, bulb, onClose, perDayUsable }) {
  const N_SHOWN = 24;
  const litCont = bulb.nCont;
  const dayBulbSeconds = bulbW > 0 ? perDayUsable / bulbW : 0;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Lightbulb size={18} color={C.amber} />
          <span style={{ fontWeight: 700, fontSize: 15, fontFamily: "var(--body)" }}>전구 시뮬레이터</span>
        </div>
        <X size={18} color={C.dim} style={{ cursor: "pointer" }} onClick={onClose} />
      </div>

      {!A.ok ? (
        <div style={{ color: C.faint, fontFamily: "var(--mono)", fontSize: 12.5, padding: "30px 0", textAlign: "center" }}>
          먼저 데이터를 분석하세요.
        </div>
      ) : (
        <>
          {/* 모드 토글 */}
          <div style={{ display: "flex", gap: 6, background: C.bg, padding: 4, borderRadius: 9, marginBottom: 14 }}>
            {[["continuous", "연속 전력"], ["budget", "에너지 예산"]].map(([m, l]) => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: "8px 0", borderRadius: 7, border: "none", cursor: "pointer",
                background: mode === m ? C.amber : "transparent", color: mode === m ? "#1a1300" : C.dim,
                fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600,
              }}>{l}</button>
            ))}
          </div>

          {/* 전구 종류 */}
          <div style={{ fontSize: 12, color: C.dim, marginBottom: 6, fontFamily: "var(--mono)" }}>전구 종류 (소비전력)</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 14 }}>
            {BULB_PRESETS.map((b) => (
              <button key={b.name} onClick={() => setBulbW(b.w)} style={{
                padding: "6px 9px", borderRadius: 7, cursor: "pointer", fontFamily: "var(--mono)", fontSize: 10.5,
                background: bulbW === b.w ? C.amber : C.panel2, color: bulbW === b.w ? "#1a1300" : C.dim,
                border: `1px solid ${bulbW === b.w ? C.amber : C.line}`, fontWeight: 600,
              }}>{b.name}</button>
            ))}
          </div>

          {/* 전구 그리드 */}
          <div style={{
            background: C.bg, border: `1px solid ${C.line}`, borderRadius: 11, padding: 16, marginBottom: 14,
          }}>
            {mode === "continuous" ? (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", gap: 9, marginBottom: 14 }}>
                  {Array.from({ length: N_SHOWN }).map((_, i) => {
                    const on = i < litCont;
                    const partial = i === litCont && bulb.fracExtra > 0.05;
                    return <BulbIcon key={i} on={on} partial={partial} frac={partial ? bulb.fracExtra : 1} />;
                  })}
                </div>
                <div style={{ textAlign: "center", fontFamily: "var(--mono)" }}>
                  <div style={{ fontSize: 32, fontWeight: 700, color: C.amber }}>{litCont}<span style={{ fontSize: 15, color: C.dim }}> 개</span></div>
                  <div style={{ fontSize: 11.5, color: C.faint, marginTop: 2 }}>
                    {fmtPower(bulb.pAvail)} 유효전력으로 {bulbW}W 전구를 <b style={{ color: C.text }}>동시에 연속</b> 점등
                  </div>
                  {litCont === 0 && <div style={{ fontSize: 11, color: C.red, marginTop: 6 }}>평균전력이 전구 1개에 못 미칩니다 (잠깐씩만 가능 → 에너지 예산 모드 참고)</div>}
                </div>
              </>
            ) : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", gap: 9, marginBottom: 14 }}>
                  {Array.from({ length: N_SHOWN }).map((_, i) => <BulbIcon key={i} on={i < budgetBulbs} frac={1} />)}
                </div>
                <Slider label="동시 점등 개수" value={budgetBulbs} min={1} max={N_SHOWN} step={1} onChange={setBudgetBulbs} fmt={(v) => `${v}개`} />
                <div style={{ textAlign: "center", fontFamily: "var(--mono)", marginTop: 6 }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: C.amber }}>{fmtTime(bulb.runtimeN)}</div>
                  <div style={{ fontSize: 11.5, color: C.faint, marginTop: 2 }}>
                    모은 유효에너지 {fmtEnergy(A.usableEnergy)}로<br />{bulbW}W 전구 {budgetBulbs}개를 점등 가능한 시간
                  </div>
                </div>
              </>
            )}
          </div>

          {/* 요약 수치 */}
          <div style={{ display: "grid", gap: 7, fontFamily: "var(--mono)", fontSize: 11.5 }}>
            <Row k="유효 에너지" v={fmtEnergy(A.usableEnergy)} />
            <Row k="유효 평균전력" v={fmtPower(A.usableAvgPower)} />
            <Row k="종단 효율 η" v={`${(A.etaTotal * 100).toFixed(1)}%`} c={C.green} />
            <Row k={`1개(${bulbW}W) 점등시간`} v={fmtTime(bulb.bulbSeconds)} />
            <div style={{ borderTop: `1px dashed ${C.line}`, margin: "4px 0" }} />
            <Row k="일일 환산 점등량" v={`${bulbW}W × ${fmtTime(dayBulbSeconds)}`} c={C.cyan} />
          </div>
          <div style={{ marginTop: 12, padding: 10, background: C.panel2, borderRadius: 8, fontSize: 10.5, color: C.faint, lineHeight: 1.6, fontFamily: "var(--mono)" }}>
            ※ 측정된 전기출력에 효율 체인(η)을 곱한 <b>유효</b> 값 기준입니다. 에너지 보존이 100% 안 되는 실제 손실을 반영합니다.
          </div>
        </>
      )}
    </div>
  );
}

const Row = ({ k, v, c }) => (
  <div style={{ display: "flex", justifyContent: "space-between" }}>
    <span style={{ color: C.dim }}>{k}</span><span style={{ color: c || C.text }}>{v}</span>
  </div>
);

function BulbIcon({ on, partial, frac = 1 }) {
  return (
    <div style={{ display: "grid", placeItems: "center", animation: on ? "glow 2.4s ease-in-out infinite" : "none" }}>
      <Lightbulb
        size={26}
        color={on ? C.amber : C.faint}
        fill={on ? (partial ? C.amber2 : C.amber) : "none"}
        style={{ opacity: on ? (partial ? 0.5 + frac * 0.5 : 1) : 0.35, transition: "all .4s" }}
      />
    </div>
  );
}

/* 인스턴스 비교 뷰 */
function CompareView({ keys }) {
  const [data, setData] = useState([]);
  useEffect(() => {
    (async () => {
      const out = [];
      for (const k of keys) {
        const v = await storeGet(k);
        if (v) { try { out.push(JSON.parse(v)); } catch {} }
      }
      setData(out);
    })();
  }, [keys.join()]);
  if (data.length < 2) return null;
  const rows = [
    ["총 에너지", (o) => fmtEnergy(o.summary.totalEnergy)],
    ["유효 에너지", (o) => fmtEnergy(o.summary.usableEnergy)],
    ["평균 전력", (o) => fmtPower(o.summary.avgPower)],
    ["첨두 전력", (o) => fmtPower(o.summary.peakPower)],
    ["측정 시간", (o) => `${o.summary.duration.toFixed(1)}s`],
    ["활성 타일", (o) => o.summary.activeTiles],
    ["종단 효율", (o) => `${(o.summary.etaTotal * 100).toFixed(1)}%`],
  ];
  return (
    <Card>
      <ChartTitle icon={GitCompare} color={C.cyan}>인스턴스 비교</ChartTitle>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 12.5 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "8px 10px", color: C.dim, borderBottom: `1px solid ${C.line}` }}>지표</th>
              {data.map((o, i) => <th key={i} style={{ textAlign: "right", padding: "8px 10px", color: i === 0 ? C.amber : C.cyan, borderBottom: `1px solid ${C.line}`, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>{o.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, fn], r) => (
              <tr key={r}>
                <td style={{ padding: "7px 10px", color: C.dim }}>{label}</td>
                {data.map((o, i) => <td key={i} style={{ padding: "7px 10px", textAlign: "right", color: C.text }}>{fn(o)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
