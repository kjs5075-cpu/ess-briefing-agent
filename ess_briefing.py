#!/usr/bin/env python3
"""
ESS 업계 주간 뉴스 브리핑 에이전트
삼성SDI ESS시스템개발 엔지니어를 위한 경쟁사 동향 및 업계 뉴스 자동 수집/발송
매주 월요일 아침 회사 이메일로 발송
"""

import feedparser
import anthropic
import smtplib
import json
import time
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────────────────────

def load_config():
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
# 검색 키워드 정의
# ─────────────────────────────────────────────────────────────

SEARCH_QUERIES = {
    "경쟁사 동향": [
        "CATL ESS battery new product 2025",
        "BYD energy storage system launch",
        "LG에너지솔루션 ESS 신제품",
        "Panasonic energy storage battery",
        "Tesla Megapack energy storage news",
        "Fluence energy storage",
        "ENVISION AESC ESS battery",
        "Sungrow energy storage system",
        "Hithium battery ESS",
    ],
    "업계 시장 동향": [
        "ESS 에너지저장장치 시장 동향",
        "grid scale energy storage market",
        "배터리 ESS 수주 계약",
        "energy storage system tender contract",
    ],
    "기술 트렌드": [
        "리튬인산철 LFP ESS 기술",
        "solid state battery ESS",
        "energy storage system fire safety",
        "배터리 ESS 효율 기술 개발",
    ],
    "정책 규제": [
        "ESS 에너지저장장치 정책 규제",
        "energy storage regulation policy 2025",
        "재생에너지 ESS 연계 정책",
    ],
    "미국 시장 동향": [
        "USA energy storage system market 2025",
        "US grid battery storage deployment",
        "America ESS utility scale project",
        "IRA inflation reduction act battery storage",
        "US energy storage capacity installation",
    ],
    "UL/NFPA 인증 규격": [
        "UL 9540 energy storage system certification",
        "NFPA 855 energy storage standard update",
        "UL 1973 battery system standard",
        "ESS fire safety certification standard",
        "energy storage system safety standard 2025",
        "LSFT large scale fire test battery ESS",
        "large scale fire testing energy storage",
    ],
}

# 중국 경쟁사 동향 — 중국어 쿼리로 별도 수집 (Google News 중국어판)
CHINA_SEARCH_QUERIES = {
    "중국 경쟁사 동향": [
        "宁德时代 储能 新产品",
        "比亚迪 储能系统",
        "阳光电源 储能",
        "海辰储能 电池",
        "亿纬锂能 储能",
        "中国 储能 出海 项目",
        "中国 储能 市场 动态",
    ],
}

# 전기신문 전용 RSS는 존재하지 않아 site: 검색으로 대체 (Google News 한국어판)
DOMESTIC_MEDIA_QUERIES = {
    "전기신문 (국내 배터리·ESS)": [
        "배터리 ESS site:electimes.com",
        "에너지저장장치 site:electimes.com",
    ],
}

# 검색 없이 피드 자체를 그대로 수집하는 해외 전문 매체 (검증된 RSS 주소)
FIXED_FEEDS = {
    "해외 전문매체 동향": [
        ("Energy-Storage.News", "https://www.energy-storage.news/feed/"),
        ("PV Magazine", "https://www.pv-magazine.com/tag/energy-storage/feed/"),
    ],
}


# ─────────────────────────────────────────────────────────────
# 뉴스 수집 (Google News RSS - 무료, API 키 불필요)
# ─────────────────────────────────────────────────────────────

GOOGLE_NEWS_LOCALES = {
    "ko": "hl=ko&gl=KR&ceid=KR:ko",
    "zh": "hl=zh-CN&gl=CN&ceid=CN:zh",
}


def fetch_google_news(query: str, days: int = 7, locale: str = "ko") -> list[dict]:
    """Google News RSS에서 최근 N일 뉴스 수집 (locale: ko=한국어, zh=중국어)"""
    encoded_query = urllib.parse.quote(query)
    locale_params = GOOGLE_NEWS_LOCALES.get(locale, GOOGLE_NEWS_LOCALES["ko"])
    url = f"https://news.google.com/rss/search?q={encoded_query}&{locale_params}"

    try:
        feed = feedparser.parse(url)
        cutoff = datetime.now() - timedelta(days=days)
        articles = []

        for entry in feed.entries[:10]:
            try:
                pub_date = datetime(*entry.published_parsed[:6])
                if pub_date >= cutoff:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": getattr(entry, "summary", "")[:400],
                        "published": pub_date.strftime("%Y-%m-%d"),
                        "source": entry.get("source", {}).get("title", ""),
                    })
            except Exception:
                continue

        return articles

    except Exception as e:
        print(f"  ⚠️  수집 오류 [{query[:30]}]: {e}")
        return []


def fetch_fixed_feed(source_name: str, url: str, days: int = 7) -> list[dict]:
    """검색 쿼리 없이 전문 매체 RSS 피드를 그대로 수집 (최근 N일)"""
    try:
        feed = feedparser.parse(url)
        cutoff = datetime.now() - timedelta(days=days)
        articles = []

        for entry in feed.entries[:15]:
            try:
                if getattr(entry, "published_parsed", None):
                    pub_date = datetime(*entry.published_parsed[:6])
                elif getattr(entry, "updated_parsed", None):
                    pub_date = datetime(*entry.updated_parsed[:6])
                else:
                    continue
                if pub_date >= cutoff:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": getattr(entry, "summary", "")[:400],
                        "published": pub_date.strftime("%Y-%m-%d"),
                        "source": source_name,
                    })
            except Exception:
                continue

        return articles

    except Exception as e:
        print(f"  ⚠️  수집 오류 [{source_name}]: {e}")
        return []


def collect_all_news() -> dict[str, list[dict]]:
    """카테고리별 뉴스 수집, 중복 제거"""
    result = {}
    seen_titles = set()

    for category, queries in SEARCH_QUERIES.items():
        category_articles = []
        for query in queries:
            articles = fetch_google_news(query)
            for article in articles:
                title_key = article["title"][:60].lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    category_articles.append(article)
            time.sleep(0.8)

        result[category] = category_articles
        print(f"  ✅ {category}: {len(category_articles)}건")

    for category, queries in DOMESTIC_MEDIA_QUERIES.items():
        category_articles = []
        for query in queries:
            articles = fetch_google_news(query, locale="ko")
            for article in articles:
                title_key = article["title"][:60].lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    category_articles.append(article)
            time.sleep(0.8)

        result[category] = category_articles
        print(f"  ✅ {category}: {len(category_articles)}건")

    for category, queries in CHINA_SEARCH_QUERIES.items():
        category_articles = []
        for query in queries:
            articles = fetch_google_news(query, locale="zh")
            for article in articles:
                title_key = article["title"][:60].lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    category_articles.append(article)
            time.sleep(0.8)

        result[category] = category_articles
        print(f"  ✅ {category}: {len(category_articles)}건")

    for category, feeds in FIXED_FEEDS.items():
        category_articles = []
        for source_name, url in feeds:
            articles = fetch_fixed_feed(source_name, url)
            for article in articles:
                title_key = article["title"][:60].lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    category_articles.append(article)
            time.sleep(0.5)

        result[category] = category_articles
        print(f"  ✅ {category}: {len(category_articles)}건")

    total = sum(len(v) for v in result.values())
    print(f"  📊 총 수집: {total}건")
    return result


# ─────────────────────────────────────────────────────────────
# AI 분석 및 브리핑 생성
# ─────────────────────────────────────────────────────────────

def build_article_text(news_by_category: dict) -> str:
    lines = []
    for category, articles in news_by_category.items():
        if not articles:
            continue
        lines.append(f"\n## [{category}]")
        for i, a in enumerate(articles[:15], 1):
            lines.append(
                f"{i}. [{a['published']}] {a['source']}\n"
                f"   제목: {a['title']}\n"
                f"   내용: {a['summary']}\n"
                f"   링크: {a['link']}"
            )
    return "\n".join(lines)


def generate_briefing(news_by_category: dict, config: dict) -> str:
    """Claude API로 브리핑 HTML 생성"""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])

    articles_text = build_article_text(news_by_category)
    week_start = (datetime.now() - timedelta(days=7)).strftime("%m/%d")
    week_end = datetime.now().strftime("%m/%d")

    prompt = f"""당신은 삼성SDI ESS시스템개발팀을 위한 업계 인텔리전스 분석가입니다.

아래 지난 1주일({week_start}~{week_end}) 동안 수집된 뉴스를 분석하여 주간 브리핑 리포트를 작성해 주세요.

수신자 프로필:
- 삼성SDI ESS시스템개발 엔지니어
- 주요 관심사: 경쟁사(CATL, BYD, LG에너지솔루션, 파나소닉, Tesla Energy, Sungrow, Hithium, EVE Energy 등 중국 업체 포함) 동향, ESS 기술 트렌드, 시장 변화. 특히 중국 ESS 업체들의 신제품·수주·해외 진출 동향에 각별히 주목할 것
- 목적: 업무에 바로 활용 가능한 경쟁 인텔리전스

=== 수집된 뉴스 (RSS 기반, 출처 명시됨) ===
{articles_text}

=== 추가 리서치 지침 (web_search 툴 사용) ===
위 RSS 수집 결과만으로 부족하면 web_search 툴로 보완하세요. 특히:
- "SNE리서치 ESS 시장", "SNE Research energy storage market" 등의 키워드로 SNE리서치 관련 최신 보고서·통계·뉴스를 검색해서 반영
- 중국 경쟁사 동향이 부족하면 "CATL储能", "比亚迪储能" 등 중국어 키워드로 추가 검색해서 보완
- UL/NFPA 인증 규격 섹션에 수집된 기사가 없다면 관련 키워드로 직접 검색해서 채우세요
- web_search로 찾은 내용은 반드시 실제 매체명/기관명을 출처로 명시하세요 (예: "SNE리서치에 따르면...", "Reuters 보도에 따르면...")
- 검색은 꼭 필요한 경우에만 사용하고, 무분별하게 여러 번 반복하지 마세요

=== 작성 요령 ===
- 핵심만 간결하게 (각 항목 2~4줄)
- 삼성SDI 관점에서 의미있는 내용 강조
- 수집된 기사와 검색 결과 모두 없는 섹션은 "이번 주 주요 동향 없음" 으로 기재
- 각 항목마다 어느 매체/기관에서 나온 정보인지 출처를 명확히 표기 (전기신문, Energy-Storage.News, PV Magazine, SNE리서치, Google News 등)
- 반드시 HTML 형식으로 작성 (아래 구조 사용)

다음 HTML 구조로 작성해 주세요. CSS 스타일은 포함하지 말고 태그만 사용:

<h2>📋 이번 주 핵심 요약</h2>
<ul>
  <li>...</li>
</ul>

<h2>🏭 경쟁사 동향</h2>
<h3>CATL</h3><p>...</p>
<h3>BYD</h3><p>...</p>
<h3>LG에너지솔루션</h3><p>...</p>
<h3>Tesla Energy</h3><p>...</p>
<h3>Sungrow / Hithium / 기타</h3><p>...</p>

<h2>📈 업계 시장 동향</h2>
<p>...</p>

<h2>🔬 기술 트렌드</h2>
<p>...</p>

<h2>📜 정책 / 규제</h2>
<p>...</p>

<h2>🇺🇸 미국 시장 동향</h2>
<p>미국 ESS 시장 주요 프로젝트, 설치 현황, IRA 정책 영향 등</p>
<p>...</p>

<h2>🇨🇳 중국 경쟁사 동향</h2>
<h3>CATL(宁德时代)</h3><p>...</p>
<h3>BYD(比亚迪)</h3><p>...</p>
<h3>Sungrow(阳光电源) / Hithium(海辰储能) / EVE(亿纬锂能) / 기타</h3><p>...</p>
<p>중국 내수 시장 동향 및 해외 진출(수출) 프로젝트</p>

<h2>📋 UL / NFPA / LSFT 인증 규격 동향</h2>
<p>UL 9540, UL 1973, NFPA 855, LSFT(Large Scale Fire Testing) 등 최신 규격 개정 및 인증 이슈</p>
<p>...</p>

<h2>💡 삼성SDI 시사점</h2>
<ul>
  <li>...</li>
</ul>

<h2>🔗 주요 기사 링크</h2>
<ul>
  <li><a href="링크">제목 (출처, 날짜)</a></li>
</ul>

중요: 최종 응답에는 "검색하겠습니다", "리포트를 작성하겠습니다" 같은 진행 상황 설명이나 안내 문구를 절대 포함하지 마세요. 마크다운 코드펜스(```)도 사용하지 마세요. <!DOCTYPE html>, <html>, <head>, <body> 같은 페이지 전체 래퍼 태그도 포함하지 마세요 — 이 콘텐츠는 이미 완성된 이메일 안에 삽입됩니다. 오직 위 구조의 <h2>로 시작하는 본문 HTML 태그만 출력하세요.
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    if message.stop_reason == "max_tokens":
        print("  ⚠️  응답이 max_tokens 한도에 도달해 잘렸을 수 있습니다.")

    # web_search로 여러 번 검색하면 실제 리포트 본문이 텍스트 블록 여러 개로
    # 쪼개져 나올 수 있고, 문장 중간에 태그가 하나도 없는 블록도 생길 수 있다.
    # 태그 유무로 블록을 골라내면 내용이 통째로 사라지므로, 모든 텍스트
    # 블록을 순서대로 그대로 이어붙인다 (HTML은 여분의 줄바꿈을 무시하므로
    # 이어붙이는 지점이 문장 중간이어도 렌더링에는 영향이 없다).
    def _strip_code_fence(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    text_blocks = [
        _strip_code_fence(block.text)
        for block in message.content
        if block.type == "text"
    ]
    briefing_html = "\n\n".join(text_blocks).strip()

    # 모델이 안내 문구나 <!DOCTYPE html>/<html>/<head>/<body> 페이지 래퍼를
    # 덧붙이는 경우가 있다. 실제 본문은 항상 <h2>로 시작하므로 그 앞부분은
    # 버리고, 끝에 남은 </body>/</html> 닫는 래퍼도 제거한다.
    start = briefing_html.find("<h2>")
    if start != -1:
        briefing_html = briefing_html[start:]
    while True:
        lowered = briefing_html.rstrip()
        if lowered.lower().endswith("</html>"):
            briefing_html = lowered[: -len("</html>")].rstrip()
        elif lowered.lower().endswith("</body>"):
            briefing_html = lowered[: -len("</body>")].rstrip()
        else:
            briefing_html = lowered
            break

    return briefing_html


# ─────────────────────────────────────────────────────────────
# 이메일 발송
# ─────────────────────────────────────────────────────────────

def build_html_email(briefing_html: str) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    week_num = datetime.now().isocalendar()[1]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', Arial, sans-serif; background: #f0f2f5; }}
  .wrap {{ max-width: 720px; margin: 24px auto; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.12); }}
  .header {{ background: linear-gradient(135deg, #1428A0 0%, #0a1a6b 100%); padding: 28px 36px; color: #fff; }}
  .header .badge {{ font-size: 11px; background: rgba(255,255,255,0.2); display: inline-block; padding: 3px 10px; border-radius: 12px; margin-bottom: 10px; letter-spacing: 1px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; }}
  .header .meta {{ font-size: 13px; opacity: 0.8; }}
  .body {{ padding: 32px 36px; color: #333; line-height: 1.75; }}
  h2 {{ font-size: 16px; color: #1428A0; border-left: 4px solid #1428A0; padding-left: 10px; margin: 28px 0 12px; }}
  h3 {{ font-size: 14px; color: #444; margin: 14px 0 6px; font-weight: 600; }}
  p {{ font-size: 14px; margin-bottom: 10px; color: #444; }}
  ul {{ padding-left: 20px; margin-bottom: 12px; }}
  li {{ font-size: 14px; margin-bottom: 6px; color: #444; }}
  a {{ color: #1428A0; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .footer {{ background: #f7f8fa; border-top: 1px solid #e8eaed; padding: 16px 36px; font-size: 12px; color: #999; display: flex; justify-content: space-between; align-items: center; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="badge">SAMSUNG SDI · ESS INTELLIGENCE</div>
    <h1>⚡ ESS 업계 주간 브리핑</h1>
    <div class="meta">{today} &nbsp;|&nbsp; {week_num}주차 &nbsp;|&nbsp; ESS시스템개발</div>
  </div>
  <div class="body">
    {briefing_html}
  </div>
  <div class="footer">
    <span>자동 생성 · Claude AI 기반 뉴스 브리핑 에이전트</span>
    <span>매주 월요일 발송</span>
  </div>
</div>
</body>
</html>"""


def send_email(briefing_html: str, config: dict):
    email_cfg = config["email"]
    today = datetime.now().strftime("%Y.%m.%d")

    recipients = email_cfg["recipient"]
    if isinstance(recipients, str):
        recipients = [recipients]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ESS 브리핑] {today} 주간 경쟁사·업계 동향"
    msg["From"] = email_cfg["sender"]
    msg["To"] = ", ".join(recipients)

    html_body = build_html_email(briefing_html)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(email_cfg["sender"], email_cfg["password"])
        server.send_message(msg)

    print(f"  ✅ 발송 완료 → {', '.join(recipients)}")


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  ESS 뉴스 브리핑 에이전트 시작")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    config = load_config()

    print("\n[1/3] 뉴스 수집 중...")
    news = collect_all_news()

    total = sum(len(v) for v in news.values())
    if total == 0:
        print("⚠️  수집된 기사가 없습니다. 네트워크 연결을 확인하세요.")
        return

    print("\n[2/3] AI 분석 및 브리핑 생성 중...")
    briefing = generate_briefing(news, config)

    print("\n[3/3] 이메일 발송 중...")
    send_email(briefing, config)

    print(f"\n{'='*55}")
    print("  완료!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
