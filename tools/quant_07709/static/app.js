const money = (value, currency) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const digits = Math.abs(value) >= 1000 ? 0 : 2;
  const formatted = Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (currency === "HKD") return `HK$${formatted}`;
  if (currency === "USD") return `$${formatted}`;
  if (currency === "KRW") return `₩${formatted}`;
  return formatted;
};

const signedPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
};

const tone = (value) => {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return "";
  return value > 0 ? "up" : "down";
};

const setText = (id, text) => {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
};

const setChange = (id, text, value) => {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = text;
  node.classList.remove("up", "down");
  const klass = tone(value);
  if (klass) node.classList.add(klass);
};

async function loadSnapshot() {
  const button = document.getElementById("refresh-btn");
  const status = document.getElementById("status-bar");
  button.disabled = true;
  button.textContent = "刷新中";
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderSnapshot(data);
    status.hidden = Object.keys(data.errors || {}).length === 0;
    if (!status.hidden) {
      status.textContent = `部分数据源失败：${Object.entries(data.errors)
        .map(([key, message]) => `${key}（${message}）`)
        .join("；")}`;
    }
  } catch (error) {
    status.hidden = false;
    status.textContent = `看板刷新失败：${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "刷新";
  }
}

function renderSnapshot(data) {
  const hk = data.quotes.hk7709 || {};
  const kr = data.quotes.kr_hynix || {};
  const us = data.quotes.us_skhy || {};
  const nav = data.official_nav || {};
  const derived = data.derived || {};

  setText("generated-at", data.generated_at || "--");
  setText("hk-price", money(hk.price, "HKD"));
  setChange("hk-change", signedPct(hk.change_pct), hk.change_pct);
  setText("hk-meta", [hk.as_of, hk.source, hk.session].filter(Boolean).join(" · ") || "暂无港股报价");

  setText("nav-price", money(nav.value, "HKD"));
  setChange("nav-premium", `HK7709 折溢价 ${signedPct(derived.official_premium_pct)}`, derived.official_premium_pct);
  setText("nav-meta", [nav.as_of, nav.source].filter(Boolean).join(" · ") || "官方净值暂不可用");

  setText("kr-price", money(kr.price, "KRW"));
  setChange("kr-change", signedPct(kr.change_pct), kr.change_pct);
  const krRef = kr.extra && kr.extra.reference_close;
  setText(
    "kr-meta",
    [
      kr.as_of,
      kr.session,
      krRef ? `参考收盘 ₩${Number(krRef).toLocaleString("en-US")}` : "",
      kr.source,
    ]
      .filter(Boolean)
      .join(" · ") || "暂无韩国报价"
  );

  setText("theory-price", money(derived.theoretical_nav, "HKD"));
  setChange(
    "theory-gap",
    `HK7709 相对理论 NAV 偏离 ${signedPct(derived.theoretical_nav_gap_pct)}`,
    derived.theoretical_nav_gap_pct
  );
  setText(
    "theory-meta",
    `按官方净值锚定价，再叠加 ${data.leverage_assumption}× 韩国当日涨跌 ${signedPct(derived.korea_return_pct)}`
  );

  setText("us-price", money(us.price, "USD"));
  setChange("us-change", signedPct(us.change_pct), us.change_pct);
  setText("us-meta", [us.as_of, us.session, us.source].filter(Boolean).join(" · ") || "暂无美股报价");

  setText("adr-premium", signedPct(derived.adr_official_premium_pct));
  document.getElementById("adr-premium").classList.remove("up", "down");
  const adrTone = tone(derived.adr_official_premium_pct);
  if (adrTone) document.getElementById("adr-premium").classList.add(adrTone);
  setText(
    "adr-compare",
    `官方价 ${money(us.price, "USD")} vs 理论价 ${money(derived.theoretical_adr_usd, "USD")}`
  );
  setText("adr-meta", `按 ${data.adr_ratio}:1 ADR 和 USD/KRW 估算，不代表可套利`);

  const warnings = document.getElementById("warnings");
  warnings.innerHTML = "";
  (data.warnings || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    warnings.appendChild(li);
  });
}

document.getElementById("refresh-btn").addEventListener("click", loadSnapshot);
loadSnapshot();
setInterval(loadSnapshot, 60_000);
