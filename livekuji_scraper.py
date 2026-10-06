import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path
import json

from playwright.sync_api import sync_playwright

TARGET_URL = "https://livekuji.com/"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
MANIFEST_PATH = DATA_DIR / "manifest.json"


def csv_output_path():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DATA_DIR / f"livekuji_cards_{timestamp}.csv"


def update_manifest(csv_filename: str):
    """manifest.json에 새 CSV 파일명 추가"""
    manifest = []
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except:
            manifest = []
    
    if csv_filename not in manifest:
        manifest.insert(0, csv_filename)
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[MANIFEST] Updated: {csv_filename} added")
    else:
        print(f"[MANIFEST] Already exists: {csv_filename}")


# 한국어/영어 둘 다 잡기 위해 정규식으로 남은 장수 추출
REMAINING_PATTERNS = [
    r"(\d+)\s*/\s*(\d+)",
    r"(\d+)\s*장\s*(?:남음|남은|잔여|재고)",
    r"(\d+)\s*(?:개|장|매|권)\s*(?:남음|남은|잔여|재고)",
    r"(\d+)\s*left",
    r"(\d+)\s*remaining",
    r"(\d+)\s*of\s*(\d+)",
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def detect_remaining(raw_text: str):
    text = normalize_text(raw_text)
    # "남은 3장", "3 / 100", "3 of 100", "3 left", "재고 30"
    patterns = [
        r"(\d+)\s*/\s*(\d+)",
        r"(\d+)\s*of\s*(\d+)",
        r"(\d+)\s*left",
        r"(\d+)\s*remaining",
        r"(\d+)\s*장\s*(?:남음|남은|잔여|재고)",
        r"(\d+)\s*(?:개|장|매|권)\s*(?:남음|남은|잔여|재고)",
        r"(\d+)\s*(?:개|장|매|권)\s*(?:남아|남음|재고)",
        r"재고\s*[:：]?\s*(\d+)",
        r"남은\s*[:：]?\s*(\d+)",
        r"잔여\s*[:：]?\s*(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        if len(m.groups()) == 2:
            current, total = m.groups()
            return {"remaining_count": int(current), "total_count": int(total), "status_text": text}
        if len(m.groups()) == 1:
            return {"remaining_count": int(m.group(1)), "total_count": None, "status_text": text}
    return {"remaining_count": None, "total_count": None, "status_text": text}


def card_title_from_element(elem):
    candidates = []
    for sel in [
        "h1", "h2", "h3", "h4", "h5",
        "strong", "b", "span", "div", "p",
    ]:
        items = elem.query_selector_all(sel)
        for item in items:
            text = normalize_text(item.text_content())
            if 1 < len(text) < 200 and not re.fullmatch(r"[\W_]+", text):
                candidates.append(text)
    if candidates:
        # 가장 긴 텍스트가 타이틀일 가능성이 높음
        return max(candidates, key=len)
    return normalize_text(elem.text_content())


def extract_cards(page):
    """실제 상품 카드가 div 안에 '남은 X / Y장' 형태로 렌더링되므로 이를 기준으로 잡는다."""
    return page.evaluate(
        """
        () => {
          const selectors = [
            'div',
            'article',
            'li',
            'a',
            '[class*="ProductCard"]',
            '[class*="product-card"]',
            '[data-testid*="product"]',
          ];

          const seen = new Set();
          const out = [];

          for (const selector of selectors) {
            const nodes = Array.from(document.querySelectorAll(selector));
            for (const node of nodes) {
              const fullText = (node.textContent || '').replace(/\s+/g, ' ').trim();
              if (!fullText || fullText.length < 12 || fullText.length > 400) continue;

              // "남은 X / Y장" 패턴이 반드시 있어야 함
              const stockMatch = fullText.match(/남은\s*(\d+)\s*\/\s*(\d+)\s*장/i);
              if (!stockMatch) continue;
              
              // 기본 필터
              const hasPrice = /\d[\d,]*(원|krw|₩)/i.test(fullText);
              const hasAction = /참여하기!|구매하기|Buy|Join/i.test(fullText);
              if (!hasPrice && !hasAction) continue;

              // 제목 추출: "남은 X / Y장" 이전 부분만
              const titlePart = fullText.split(/남은\s*\d+\s*\/\s*\d+\s*장/i)[0];
              let title = titlePart
                .replace(/^(피가쿠지|KUJI-PLAY|즉시구매|공식쿠지|2쿠지|쿠지|구매|공식|마켓|토이|모리|라이브온|LIVE ON|OZ)+\\s*/gi, '')
                .replace(/^(set\\.|set\\))+\\s*/gi, '')
                .replace(/^\\d+\\)\\s*/g, '')
                .replace(/\\s*(할인|discount|off|\\d+%)/gi, '')
                .replace(/[^가-힣A-Za-z0-9\\s~().!\\-]/g, '')
                .replace(/\\s+/g, ' ')
                .trim();
              
              // 제목 검증: 너무 짧으면 제외
              if (!title || title.length < 2 || /^[^가-힣A-Za-z0-9]+$/.test(title)) continue;

              const href = node.href || node.querySelector('a')?.href || '';
              const key = (href || fullText).slice(0, 200);
              if (seen.has(key)) continue;
              seen.add(key);

              out.push({
                text: fullText,
                href,
                title: title,
                remaining: parseInt(stockMatch[1], 10),
                total: parseInt(stockMatch[2], 10),
                hasSoldOut: /품절|SOLD OUT|out of stock/i.test(fullText) && parseInt(stockMatch[1], 10) === 0,
              });
            }
          }

          return out;
        }
        """
    )


def debug_dump_candidates(page, limit=30):
    """실제 DOM에서 어떤 노드들이 상품 후보인지 빠르게 점검한다."""
    result = page.evaluate(
        """
        () => {
          const candidates = [];
          const selectors = ['article', 'li', 'a', 'div', 'section'];
          for (const selector of selectors) {
            const nodes = document.querySelectorAll(selector);
            for (const node of nodes) {
              const text = (node.textContent || '').replace(/\s+/g, ' ').trim();
              if (!text || text.length < 12 || text.length > 400) continue;
              const lower = text.toLowerCase();
              const isLikely = /(sold out|품절|남음|재고|left|remaining|원|krw|₩|\d+\/\d+|\d+장)/i.test(lower) || !!node.querySelector('img');
              if (isLikely) {
                candidates.push({
                  tag: node.tagName,
                  text: text.slice(0, 200),
                  className: node.className || '',
                  href: node.href || '',
                  img: !!node.querySelector('img')
                });
              }
            }
          }
          return candidates.slice(0, 80);
        }
        """
    )
    print("[DEBUG] candidate count:", len(result))
    for item in result[:limit]:
        print("-", item)


def click_more_if_exists(page):
    buttons = page.locator("button, a")
    found = False
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        text = normalize_text(btn.text_content())
        low = text.lower()
        if "더보기" in text or "more" in low or "view more" in low or "more products" in low:
            try:
                btn.scroll_into_view_if_needed()
                btn.click(timeout=5000)
                found = True
                break
            except Exception:
                pass
    return found


def close_modal_if_any(page):
    """자주 보이는 팝업/모달을 자동으로 닫아 페이지 접근을 가능하게 한다."""
    selectors = [
        "button",
        "[role='button']",
        "[aria-label]",
        "[data-testid*='close']",
        "[class*='modal'] button",
        "[class*='dialog'] button",
        "[class*='popup'] button",
    ]
    close_keywords = ["닫기", "close", "x", "확인", "ok", "동의", "agree", "later", "나중에", "취소"]

    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = loc.count()
            for i in range(min(count, 40)):
                btn = loc.nth(i)
                try:
                    text = normalize_text(btn.text_content())
                    aria = btn.get_attribute("aria-label") or ""
                    combined = f"{text} {aria}".lower()
                    if any(keyword.lower() in combined for keyword in close_keywords):
                        try:
                            btn.scroll_into_view_if_needed()
                            btn.click(timeout=3000)
                            return True
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    try:
        dialog = page.locator("[role='dialog'], [class*='modal'], [class*='popup']").first
        if dialog.count() > 0:
            btn = dialog.locator("button, [role='button']").first
            if btn.count() > 0:
                btn.click(timeout=3000)
                return True
    except Exception:
        pass

    return False


def clean_card(entry):
    """extract_cards에서 받은 데이터를 정제해서 CSV 행으로 변환"""
    title = normalize_text(entry.get("title") or "")
    text = normalize_text(entry.get("text") or "")
    
    # extract_cards에서 이미 추출한 값 사용
    remaining = entry.get("remaining")
    total = entry.get("total")
    
    sold_out = bool(entry.get("hasSoldOut"))

    result = {
        "title": title[:200],
        "href": entry.get("href") or "",
        "sold_out": sold_out,
        "remaining_count": remaining,
        "total_count": total,
        "status_text": text[:300],
        "raw_text": text[:500],
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }

    if sold_out:
        result["stock_state"] = "SOLD OUT"
    elif remaining is not None and total is not None:
        result["stock_state"] = f"{remaining} left"
    else:
        result["stock_state"] = "unknown"

    return result


def main():
    output_path = csv_output_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_page(viewport={"width": 1600, "height": 2200}, locale="ko-KR")
        page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        print("[LOAD] 페이지 로드 완료, 5초 대기 중...")
        page.wait_for_timeout(5000)
        close_modal_if_any(page)
        page.wait_for_timeout(1000)

        rows = []
        seen_keys = set()

        for cycle in range(30):
            cards = extract_cards(page)
            print(f"[CYCLE {cycle}] candidate cards: {len(cards)}")
            if len(cards) == 0:
                print("[DEBUG] no product candidates detected, dumping DOM candidates...")
                debug_dump_candidates(page)

            for entry in cards:
                item = clean_card(entry)
                key = (item["title"], item["href"], item["raw_text"][:120])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(item)

            if not click_more_if_exists(page):
                print("[INFO] 더보기 버튼이 없거나 마지막 페이지입니다.")
                break

            page.wait_for_timeout(1200)

        fieldnames = [
            "collected_at",
            "title",
            "href",
            "sold_out",
            "remaining_count",
            "total_count",
            "stock_state",
            "status_text",
            "raw_text",
        ]

        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})

        print(f"[SAVE] {len(rows)} rows saved to {output_path.resolve()}")
        
        # manifest.json 자동 업데이트
        update_manifest(output_path.name)
        if rows:
            print("[RESULT] 마지막 수집된 항목들:")
            for row in rows[-10:]:
                print(row)
        else:
            print("[RESULT] 추출된 카드가 없습니다. DOM 후보를 로그에 출력했습니다.")

        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        raise
