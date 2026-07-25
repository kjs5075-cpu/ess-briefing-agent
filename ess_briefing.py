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


# ─────────────────────────────────────────────────────────────
# 뉴스 수집 (Google News RSS - 무료, API 키 불필요)
# ─────────────────────────────────────────────────────────────

def fetch_google_news(query: str, days: int = 7) -> list[dict]:
    """Google News RSS에서 최근 N일 뉴스 수집"""
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

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
- 주요 관심사: 경쟁사(CATL, BYD, LG에너지솔루션, 파나소닉, Tesla Energy 등) 동향, ESS 기술 트렌드, 시장 변화
- 목적: 업무에 바로 활용 가능한 경쟁 인텔리전스

=== 수집된 뉴스 ===
{articles_text}

=== 작성 요령 ===
- 핵심만 간결하게 (각 항목 2~4줄)
- 삼성SDI 관점에서 의미있는 내용 강조
- 수집된 기사가 없는 섹션은 "이번 주 주요 동향 없음" 으로 기재
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
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ESS 브리핑] {today} 주간 경쟁사·업계 동향"
    msg["From"] = email_cfg["sender"]
    msg["To"] = email_cfg["recipient"]

    html_body = build_html_email(briefing_html)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(email_cfg["sender"], email_cfg["password"])
        server.send_message(msg)

    print(f"  ✅ 발송 완료 → {email_cfg['recipient']}")


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
