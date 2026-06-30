"""
Football League Scraper v2.0
============================
Streamlit app для збору даних з футбольних сайтів.
Базується на: MoAshour93/Construction_Crawl4AI_WebScraper (Apache-2.0)

Зміни у v2.0:
- Додано Playwright для JS-сторінок (FBRef та ін.)
- Автоматичний збір по 3 лігах одним кліком
- Збереження CSV у папку /output/ з датою
- Розумний вибір методу: спочатку requests, потім Playwright
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import markdownify
import pandas as pd
import re
import io
import os
from datetime import datetime
from pathlib import Path

# ─── Перевірка чи є Playwright ────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ─── Папка для збереження файлів ──────────────────────────────────────────────
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── Список ліг для автозбору ─────────────────────────────────────────────────
LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {
        "url": "https://fbref.com/en/comps/9/Premier-League-Stats",
        "file": "premier_league",
    },
    "🇪🇸 La Liga": {
        "url": "https://fbref.com/en/comps/12/La-Liga-Stats",
        "file": "la_liga",
    },
    "🇩🇪 Bundesliga": {
        "url": "https://fbref.com/en/comps/20/Bundesliga-Stats",
        "file": "bundesliga",
    },
}

# ─── Налаштування сторінки ────────────────────────────────────────────────────
st.set_page_config(
    page_title="⚽ Football League Scraper v2",
    page_icon="⚽",
    layout="wide",
)

# ─── CSS стилі ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        font-size: 1rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .stButton > button {
        background-color: #16213e;
        color: white;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        font-size: 1rem;
        border: none;
    }
    .stButton > button:hover {
        background-color: #0f3460;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 10px 15px;
        border-radius: 4px;
        margin: 10px 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 10px 15px;
        border-radius: 4px;
        margin: 10px 0;
    }
    .error-box {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 10px 15px;
        border-radius: 4px;
        margin: 10px 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border-left: 4px solid #17a2b8;
        padding: 10px 15px;
        border-radius: 4px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ─── Заголовок ────────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">⚽ Football League Scraper v2.0</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Автоматичний збір даних — Прем\'єр-ліга, Ла-Ліга, Бундесліга</div>', unsafe_allow_html=True)

# ─── Статус Playwright ────────────────────────────────────────────────────────
if PLAYWRIGHT_AVAILABLE:
    st.markdown("""
    <div class="success-box">
    ✅ <b>Playwright встановлено</b> — JS-сторінки (FBRef) підтримуються
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="warning-box">
    ⚠️ <b>Playwright не знайдено</b> — використовується базовий режим (requests).<br>
    Для FBRef встанови: <code>pip install playwright && playwright install chromium</code>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ════════════════════════════════════════════════════════════════════════════════
# ФУНКЦІЇ
# ════════════════════════════════════════════════════════════════════════════════

def fetch_with_requests(url: str) -> tuple[str | None, str | None]:
    """Базовий метод — requests + BeautifulSoup. Швидко, але не бачить JS."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text, None
    except requests.exceptions.Timeout:
        return None, "⏱️ Час очікування вийшов (15 сек)."
    except requests.exceptions.HTTPError as e:
        return None, f"❌ HTTP помилка: {e}"
    except requests.exceptions.ConnectionError:
        return None, "🔌 Не вдалося підключитися."
    except Exception as e:
        return None, f"❌ Помилка: {e}"


def fetch_with_playwright(url: str) -> tuple[str | None, str | None]:
    """
    Playwright — запускає справжній браузер Chrome.
    Чекає поки JS завантажить дані, потім забирає HTML.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None, "Playwright не встановлено."
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            # Чекаємо до 30 сек поки сторінка повністю завантажиться
            page.goto(url, wait_until="networkidle", timeout=30000)
            # Додаткова пауза для JS-таблиць
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            return html, None
    except Exception as e:
        return None, f"❌ Playwright помилка: {e}"


def fetch_html(url: str, use_playwright: bool = False) -> tuple[str | None, str | None, str]:
    """
    Головна функція завантаження.
    Якщо use_playwright=True і Playwright є — спочатку пробує Playwright.
    Інакше — спочатку requests, потім fallback на Playwright.
    """
    if use_playwright and PLAYWRIGHT_AVAILABLE:
        html, error = fetch_with_playwright(url)
        if html:
            return html, None, "playwright"
        fallback_html, fallback_error = fetch_with_requests(url)
        if fallback_html:
            return fallback_html, None, "requests"
        return None, f"{error} | {fallback_error}", "none"

    html, error = fetch_with_requests(url)
    if html:
        return html, None, "requests"
    if PLAYWRIGHT_AVAILABLE:
        html_pw, error_pw = fetch_with_playwright(url)
        if html_pw:
            return html_pw, None, "playwright"
        return None, f"{error} | {error_pw}", "none"
    return None, error, "none"


def html_to_markdown(html: str) -> str:
    """Конвертує HTML у читабельний Markdown."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head", "iframe", "noscript"]):
        tag.decompose()
    md = markdownify.markdownify(str(soup), heading_style="ATX", strip=["a"])
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def extract_tables(html: str) -> list[pd.DataFrame]:
    """Витягує всі HTML-таблиці як DataFrame."""
    try:
        return pd.read_html(io.StringIO(html))
    except Exception:
        return []


def clean_table(df: pd.DataFrame) -> pd.DataFrame:
    """Прибирає порожні рядки/стовпці."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def save_csv_to_output(df: pd.DataFrame, filename: str) -> str:
    """Зберігає CSV у папку /output/ і повертає шлях."""
    filepath = OUTPUT_DIR / filename
    df.to_csv(filepath, index=False, encoding="utf-8")
    return str(filepath)


# ════════════════════════════════════════════════════════════════════════════════
# РЕЖИМ 1: АВТОЗБІР ТРЬОХ ЛІГ
# ════════════════════════════════════════════════════════════════════════════════

st.markdown("## 🤖 Автоматичний збір — 3 ліги")
st.markdown("Натисни одну кнопку — програма сама зайде на всі три сайти і збереже дані.")

use_pw_auto = st.checkbox(
    "Використовувати Playwright (браузер) — рекомендовано для FBRef",
    value=PLAYWRIGHT_AVAILABLE,
    disabled=not PLAYWRIGHT_AVAILABLE,
    key="pw_auto"
)

auto_btn = st.button("🚀 Зібрати всі 3 ліги", use_container_width=False)

if auto_btn:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_summary = []

    for league_name, league_info in LEAGUES.items():
        st.markdown(f"---\n### {league_name}")
        url = league_info["url"]
        st.caption(f"URL: {url}")

        with st.spinner(f"⏳ Завантажую {league_name}..."):
            html, error, used_method = fetch_html(url, use_playwright=use_pw_auto)
            used_method = used_method or ("playwright" if use_pw_auto else "requests")

        if error:
            st.markdown(f'<div class="error-box">❌ {league_name}: {error}</div>', unsafe_allow_html=True)
            results_summary.append({"Ліга": league_name, "Статус": "❌ Помилка", "Таблиць": 0, "Файл": "—"})
            continue

        tables = extract_tables(html)
        tables = [clean_table(df) for df in tables if not clean_table(df).empty]

        if not tables:
            st.markdown(f'<div class="warning-box">⚠️ Сторінку завантажено, але таблиць не знайдено. Можливо сайт заблокував або потрібен Playwright.</div>', unsafe_allow_html=True)
            results_summary.append({"Ліга": league_name, "Статус": "⚠️ Без таблиць", "Таблиць": 0, "Файл": "—"})
            continue

        # Зберігаємо першу таблицю (основна таблиця ліги) як CSV
        main_table = tables[0]
        filename = f"{league_info['file']}_{timestamp}.csv"
        saved_path = save_csv_to_output(main_table, filename)

        st.success(f"✅ Знайдено {len(tables)} таблиць. Збережено: {saved_path}")

        with st.expander(f"📋 Переглянути головну таблицю ({len(main_table)} рядків)"):
            st.dataframe(main_table, use_container_width=True)
            st.download_button(
                label=f"⬇️ Завантажити CSV — {league_name}",
                data=df_to_csv_bytes(main_table),
                file_name=filename,
                mime="text/csv",
                key=f"auto_{league_info['file']}",
            )

        results_summary.append({
            "Ліга": league_name,
            "Статус": "✅ Успіх",
            "Таблиць": len(tables),
            "Файл": saved_path,
        })

    # Підсумкова таблиця
    st.divider()
    st.markdown("### 📊 Підсумок збору")
    summary_df = pd.DataFrame(results_summary)
    st.dataframe(summary_df, use_container_width=True)

st.divider()

# ════════════════════════════════════════════════════════════════════════════════
# РЕЖИМ 2: РУЧНИЙ ЗБІР (як у v1.0)
# ════════════════════════════════════════════════════════════════════════════════

st.markdown("## 🔧 Ручний режим — будь-який URL")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown("**📚 Тест**")
    st.code("https://books.toscrape.com", language=None)
with col2:
    st.markdown("**🏴󠁧󠁢󠁥󠁮󠁧󠁿 PL**")
    st.code("https://fbref.com/en/comps/9/Premier-League-Stats", language=None)
with col3:
    st.markdown("**🇪🇸 La Liga**")
    st.code("https://fbref.com/en/comps/12/La-Liga-Stats", language=None)
with col4:
    st.markdown("**🇩🇪 Bundesliga**")
    st.code("https://fbref.com/en/comps/20/Bundesliga-Stats", language=None)

url_manual = st.text_input(
    "🌐 Вставте URL сторінки:",
    placeholder="https://books.toscrape.com",
)

use_pw_manual = st.checkbox(
    "Використовувати Playwright для цього URL",
    value=False,
    disabled=not PLAYWRIGHT_AVAILABLE,
    key="pw_manual"
)

col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    scrape_btn = st.button("🚀 Зібрати дані", use_container_width=True)

if scrape_btn:
    if not url_manual or not url_manual.startswith("http"):
        st.error("⚠️ Введи правильний URL (починається з http:// або https://)")
    else:
        method = "Playwright 🌐" if (use_pw_manual and PLAYWRIGHT_AVAILABLE) else "requests ⚡"
        with st.spinner(f"⏳ Завантажую через {method}..."):
            html, error, used_method = fetch_html(url_manual, use_playwright=use_pw_manual)
            method = "Playwright 🌐" if used_method == "playwright" else "requests ⚡"

        if error:
            st.error(error)
            st.markdown("""
            <div class="warning-box">
            <b>💡 Що спробувати:</b><br>
            • Перевір що URL правильний<br>
            • Увімкни Playwright для JS-сайтів<br>
            • Спробуй спочатку <code>https://books.toscrape.com</code>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="success-box">
            ✅ Завантажено через {method}! ({len(html):,} символів HTML)
            </div>
            """, unsafe_allow_html=True)

            tab1, tab2, tab3 = st.tabs(["📄 Markdown", "📊 Таблиці (CSV)", "🔍 Сирий HTML"])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            with tab1:
                md_content = html_to_markdown(html)
                st.text_area("Результат:", md_content, height=400)
                st.download_button(
                    label="⬇️ Завантажити .md",
                    data=md_content.encode("utf-8"),
                    file_name=f"scraped_{timestamp}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            with tab2:
                tables = extract_tables(html)
                if not tables:
                    st.info("ℹ️ Таблиць не знайдено. Спробуй Wikipedia або увімкни Playwright.")
                else:
                    st.success(f"✅ Знайдено {len(tables)} таблиць")
                    for i, df in enumerate(tables):
                        df = clean_table(df)
                        if df.empty:
                            continue
                        filename = f"manual_table_{i+1}_{timestamp}.csv"
                        save_csv_to_output(df, filename)
                        with st.expander(f"📋 Таблиця {i+1} ({len(df)} рядків × {len(df.columns)} стовпців)"):
                            st.dataframe(df, use_container_width=True)
                            st.download_button(
                                label=f"⬇️ CSV таблиця {i+1}",
                                data=df_to_csv_bytes(df),
                                file_name=filename,
                                mime="text/csv",
                                key=f"manual_csv_{i}",
                            )

            with tab3:
                st.code(html[:3000], language="html")

# ─── Підказки ─────────────────────────────────────────────────────────────────
st.divider()
with st.expander("❓ Як користуватися v2.0"):
    st.markdown("""
    **Автоматичний режим (зверху):**
    1. Увімкни Playwright якщо встановлено
    2. Натисни «Зібрати всі 3 ліги»
    3. Чекай — програма сама обробить кожен сайт
    4. CSV файли збережуться у папку `/output/`

    **Ручний режим (знизу):**
    - Як раніше — вставляєш URL і натискаєш кнопку
    - Тепер можна увімкнути Playwright для JS-сторінок

    **Встановлення Playwright (якщо ще немає):**
    ```bash
    pip install playwright
    playwright install chromium
    ```

    **Якщо FBRef блокує:**
    - Це нормально — сайт захищений від ботів
    - Спробуй Wikipedia для тесту таблиць
    - Фаза 5: розглянути платний API
    """)

st.markdown(
    "<div style='text-align:center; color:#aaa; font-size:0.75rem; margin-top:1rem;'>"
    "Football Scraper v2.0 · Базується на MoAshour93/Construction_Crawl4AI_WebScraper (Apache-2.0)"
    "</div>",
    unsafe_allow_html=True
)
