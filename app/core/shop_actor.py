"""Open SHOP, click cash ALL, then click lit gold/green BUY. Never grey LEVEL."""

from __future__ import annotations

import time

from app.core.click_map import ClickMap, subtab_key
from app.core.input import click_at, click_tab, focus_window, is_roblox_chrome, scroll_at
from app.core.jobs import shift_words
from app.core.labels import label_key, labels_match
from app.core.ocr_engine import OCRWord
from app.core.shop import (
    BUY_COL,
    CASH_COL,
    ROBUX_COL,
    can_afford,
    cash_hud_grain,
    catalog_price,
    equipment_all_click,
    find_equipment_all,
    find_lit_cash_buys,
    find_row_cash_buy,
    has_shop_list_words,
    parse_shop_rows,
    parse_stock_timer,
    shop_names_match,
)


class ShopActor:
    def __init__(self) -> None:
        self._last_click = 0.0
        self._scrolls = 0
        self._went_top = False
        self._halt = False
        self._paused = False
        self._opened = False
        self._section = "All"
        self._clicked: set[str] = set()
        self._clicked_ys: set[int] = set()
        self._misses: dict[str, int] = {}
        self._pending = ""
        self._cash_before: int | None = None
        self._pending_price: int | None = None
        self._last_view = ""
        self._stuck = 0
        self._second_pass = False
        self._ocr_miss = 0
        self._reopens = 0
        self.pass_done = False
        self.restock_left = None

    def halt(self) -> None:
        self._halt = True

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    def reset(self) -> None:
        self._halt = False
        self._paused = False
        self._scrolls = 0
        self._went_top = False
        self._opened = False
        self._section = "All"
        self._clicked = set()
        self._clicked_ys = set()
        self._misses = {}
        self._pending = ""
        self._cash_before = None
        self._pending_price = None
        self._last_view = ""
        self._stuck = 0
        self._second_pass = False
        self._ocr_miss = 0
        self._reopens = 0
        self.pass_done = False
        self.restock_left = None

    def _aborted(self) -> bool:
        return self._halt or self._paused

    def _sleep(self, seconds: float) -> bool:
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if self._aborted():
                return False
            time.sleep(0.05)
        return True

    def step(self, engine, info, frame, wanted, cash: int | None, activity, grab=None, catalog=None) -> bool:
        if self._aborted() or frame is None or info is None:
            return False
        if time.time() - self._last_click < 0.25:
            return False
        if not self._opened:
            if not self._open_shop(engine, info, activity, grab):
                return False
            self._went_top = self._scrolls > 0
            return False

        if not self._went_top:
            activity("Scrolling Shop to the top before BUY")
            self._seek(info, activity)
            return False

        words = self._list_words(engine, frame)
        texts = [word.text for word in words]
        self._fresh_stock(parse_stock_timer(texts), activity)
        rows = [row for row in parse_shop_rows(words, frame, section="All") if not row.gold]
        if not rows:
            if cash is not None and cash > 0 and self._click_lit_buy(info, frame, activity, cash):
                self._ocr_miss = 0
                return True
            return self._empty_list(activity)
        self._ocr_miss = 0

        if cash is None:
            activity("Cash on hand not read — waiting before BUY")
            return False
        self._confirm_purchase(cash, activity)
        if cash <= 0:
            self.pass_done = True
            activity("No cash on hand — shop pass finished")
            return False

        buy_all = not wanted
        priced = []
        for row in rows:
            if wanted and not any(shop_names_match(item.name, row.name) for item in wanted):
                continue
            key = label_key(row.name)
            if key in self._clicked:
                continue
            price = catalog_price(row, catalog)
            if price is not None and not can_afford(cash, price):
                activity(f"{row.name}: skip — {row.cash_text or price} is more than cash on hand")
                continue
            priced.append((price if price is not None else 10**15, row))
        priced.sort(key=lambda item: (item[0], item[1].y, item[1].name))
        for price, row in priced:
            gold = find_row_cash_buy(frame, words, row.y or 0, row.height or 24)
            if gold is None:
                activity(f"{row.name}: no gold BUY on this row (LEVEL lock or grey)")
                continue
            cx, cy = gold
            x = info.left + cx
            y = info.top + cy
            if is_roblox_chrome(info, x, y) or cx < int(frame.shape[1] * BUY_COL) or cx >= int(frame.shape[1] * ROBUX_COL):
                activity(f"{row.name}: skip — that BUY is Robux Shop, not cash")
                continue
            if self._aborted() or not focus_window(info.hwnd):
                return False
            tag = row.cash_text or ("lit BUY" if price >= 10**14 else f"${int(price):,}")
            activity(f"Clicking lit BUY: {row.name} ({tag}) at {x},{y}")
            if not click_at(info, x, y):
                activity("BUY click failed")
                return False
            key = label_key(row.name)
            self._clicked.add(key)
            self._clicked_ys.add(int(cy / 28))
            self._pending = key
            self._cash_before = cash
            self._pending_price = None if price >= 10**14 else int(price)
            self._last_click = time.time()
            self._sleep(0.12)
            return True

        if buy_all and self._click_lit_buy(info, frame, activity, cash):
            return True

        shown = ", ".join(row.name for row in rows[:4])
        looking = "affordable lit BUY on ALL" if buy_all else "ticked shop items you can afford"
        activity(f"Looking for {looking}. Visible: {shown or 'none'}. Moving the list.")
        view = "|".join(label_key(row.name) for row in rows[:6])
        if view and view == self._last_view:
            self._stuck += 1
        else:
            self._stuck = 0
            self._last_view = view
        self._seek(info, activity)
        if self._stuck >= 3:
            self._clicked_ys.clear()
            if buy_all and self._click_lit_buy(info, frame, activity, cash):
                return True
            if not self._second_pass:
                self._second_pass = True
                self._went_top = False
                self._stuck = 0
                self._last_view = ""
                activity("Shop list stuck — back to the top for leftover gold BUY")
                return False
            self.pass_done = True
            activity("Shop pass finished — no more affordable gold BUY on this stock")
        return False

    def _fresh_stock(self, timer: int | None, activity) -> None:
        if timer is not None and self.restock_left is not None and timer > self.restock_left + 20:
            self._clicked.clear()
            self._clicked_ys.clear()
            self._second_pass = False
            self._stuck = 0
            self.pass_done = False
            activity("New shop stock — buying gold BUY again")
        self.restock_left = timer

    def _empty_list(self, activity) -> bool:
        self._ocr_miss += 1
        if self._ocr_miss < 3:
            activity("Waiting for shop list OCR")
            return False
        self._reopens += 1
        self._opened = False
        self._ocr_miss = 0
        self._clicked_ys.clear()
        activity("SHOP list not read — opening ALL")
        return False

    def _confirm_purchase(self, cash: int, activity) -> None:
        name = self._pending
        if not name:
            return
        before = self._cash_before
        price = self._pending_price
        self._pending = ""
        self._cash_before = None
        self._pending_price = None
        grain = cash_hud_grain(before if before is not None else cash)
        spent = before is not None and cash < before - max(500, grain // 4)
        tiny = (
            price is not None
            and price < grain
            and before is not None
            and cash <= before + grain
        )
        if spent:
            activity(f"Bought — cash dropped after {name}")
            return
        self._misses[name] = self._misses.get(name, 0) + 1
        if tiny and self._misses[name] >= 2:
            activity(f"Bought {name} — cash HUD cannot show a spend that small")
            return
        self._clicked.discard(name)
        if self._misses[name] >= 2:
            self._clicked.add(name)
            activity(f"{name}: BUY did not spend cash — leaving that row")
        elif tiny:
            activity(f"{name}: cash HUD did not move — trying that row again")
        else:
            activity(f"{name}: BUY did not spend cash — trying that row again")

    def _open_shop(self, engine, info, activity, grab=None) -> bool:
        clicks = ClickMap.load()
        shop = clicks.screen_point("tab_shop", info)
        if shop is None or info is None:
            return False
        if not focus_window(info.hwnd):
            return False
        activity(f"Clicking taught SHOP at {shop[0]},{shop[1]}")
        click_tab(info, *shop)
        if not self._sleep(0.10):
            return False
        cash = clicks.screen_point("shop_cash", info)
        if cash is not None:
            activity(f"Clicking taught EQUIPMENT (CASH) at {cash[0]},{cash[1]}")
            click_at(info, *cash)
            if not self._sleep(0.08):
                return False
        elif grab is not None and engine is not None:
            fresh = grab()
            if fresh is not None:
                self._click_equipment_cash(engine, info, fresh, activity)
        if not self._click_all(engine, info, activity, grab, clicks):
            return False
        self._section = "All"
        self._opened = True
        activity("Shop EQUIPMENT (CASH) ALL is open")
        return True

    def _click_all(self, engine, info, activity, grab, clicks) -> bool:
        found = None
        if grab is not None and engine is not None:
            if not self._sleep(0.16):
                return False
            fresh = grab()
            if fresh is not None:
                found = find_equipment_all(self._header_words(engine, fresh), fresh)
        if found is not None:
            x = info.left + found[0]
            y = info.top + found[1]
            activity(f"Clicking ALL at {x},{y}")
            click_at(info, x, y)
            return self._sleep(0.20)
        point = clicks.screen_point("shop_all", info) or clicks.screen_point(subtab_key("SHOP", "ALL"), info)
        if point is not None and (point[0] - info.left) < int(info.width * 0.38):
            activity(f"Clicking taught ALL at {point[0]},{point[1]}")
            click_at(info, *point)
            return self._sleep(0.20)
        vehicles = clicks.screen_point("shop_vehicles", info)
        vx = (vehicles[0] - info.left, vehicles[1] - info.top) if vehicles is not None else None
        ax, ay = equipment_all_click(info.width, info.height, vx)
        x = info.left + ax
        y = info.top + ay
        activity(f"Clicking cash ALL at {x},{y} (left of WEAPONS)")
        click_at(info, x, y)
        return self._sleep(0.20)

    def _click_lit_buy(self, info, frame, activity, cash: int | None = None) -> bool:
        for cx, cy in find_lit_cash_buys(frame):
            bucket = int(cy / 28)
            if bucket in self._clicked_ys:
                continue
            x = info.left + cx
            y = info.top + cy
            if is_roblox_chrome(info, x, y) or cx < int(frame.shape[1] * BUY_COL) or cx >= int(frame.shape[1] * ROBUX_COL):
                continue
            if self._aborted() or not focus_window(info.hwnd):
                return False
            activity(f"Clicking lit BUY at {x},{y}")
            if not click_at(info, x, y):
                activity("BUY click failed")
                return False
            self._clicked_ys.add(bucket)
            self._pending = f"LITBUY{bucket}"
            self._cash_before = cash
            self._pending_price = 500
            self._last_click = time.time()
            self._sleep(0.12)
            return True
        return False

    def _header_words(self, engine, frame) -> list[OCRWord]:
        if frame is None:
            return []
        height, width = frame.shape[:2]
        x1 = int(width * 0.12)
        y1 = int(height * 0.16)
        x2 = int(width * 0.50)
        y2 = int(height * 0.38)
        crop = frame[y1:y2, x1:x2]
        return shift_words(engine.words(crop, min_confidence=16), x1, y1, scale=1.0)

    def _click_equipment_cash(self, engine, info, frame, activity) -> None:
        words = self._list_words(engine, frame)
        for word in words:
            key = label_key(word.text)
            if "ROBUX" in key or "GAMEPASS" in key:
                continue
            if "EQUIPMENT" not in key and not labels_match(word.text, "EQUIPMENT (CASH)"):
                continue
            if word.x > int(frame.shape[1] * 0.55):
                continue
            x = info.left + word.cx
            y = info.top + word.cy
            activity(f"Clicking EQUIPMENT (CASH) at {x},{y}")
            click_at(info, x, y)
            self._sleep(0.08)
            return

    def _list_words(self, engine, frame) -> list[OCRWord]:
        if frame is None:
            return []
        height, width = frame.shape[:2]
        x1 = int(width * 0.14)
        y1 = int(height * 0.08)
        x2 = int(width * CASH_COL)
        y2 = int(height * 0.90)
        crop = frame[y1:y2, x1:x2]
        words = shift_words(engine.words(crop, min_confidence=22), x1, y1, scale=1.0)
        if has_shop_list_words(words):
            return words
        full = engine.words(frame, min_confidence=22)
        return [word for word in full if x1 <= word.x < x2 and y1 <= word.y < y2]

    def _seek(self, info, activity) -> None:
        if self._aborted() or info is None:
            return
        clicks = ClickMap.load()
        taught = clicks.scroll_point("SHOP", info)
        if taught is not None and (taught[0] - info.left) >= int(info.width * CASH_COL):
            taught = None
        if taught is not None:
            sx, sy = taught
        else:
            sx = info.left + int(info.width * 0.42)
            sy = info.top + int(info.height * 0.52)
        if not focus_window(info.hwnd):
            return
        if not self._went_top:
            activity("Scrolling Shop to the top")
            scroll_at(sx, sy, steps=5)
            self._went_top = True
            self._scrolls += 1
            self._clicked_ys.clear()
            self._sleep(0.12)
            return
        activity("Scrolling down Shop")
        scroll_at(sx, sy, steps=-3)
        self._scrolls += 1
        self._clicked_ys.clear()
        self._sleep(0.12)
