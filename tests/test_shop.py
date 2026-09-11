import unittest

import cv2
import numpy as np

from app.core.ocr_engine import OCRWord
from app.core.shop import find_cash_buy_button, parse_shop_rows, shop_catalog_payload
from app.core.playbook import Playbook


FRAME = np.zeros((720, 1920, 3), dtype=np.uint8)


def _word(text, x, y, w=80, h=20):
    return OCRWord(text=text, x=x, y=y, width=w, height=h, confidence=90)


def _paint_buy(frame, x, y, w=90, h=28, hue=50):
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    hsv[:] = (hue, 180, 200)
    frame[int(y):int(y) + h, int(x):int(x) + w] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return int(x) + w // 2, int(y) + h // 2


class ShopTests(unittest.TestCase):
    def test_cash_row_not_gold(self):
        words = [
            _word("Switch Stiletto", 360, 400, 140, 22),
            _word("$500", 980, 404, 60, 20),
            _word("BUY", 1100, 402, 70, 24),
        ]
        rows = parse_shop_rows(words, FRAME)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Switch Stiletto")
        self.assertEqual(rows[0].cash, 500)
        self.assertFalse(rows[0].gold)

    def test_row_stats_match_the_game(self):
        from app.core.shop import format_shop_stats, harvest_shop_from_words
        words = [
            _word("COMMON WEAPON", 360, 372, 140, 16),
            _word("Switch Stiletto", 360, 400, 160, 22),
            _word("+3 Attack", 360, 426, 90, 16),
            _word("Owned: 1", 360, 448, 80, 16),
            _word("$500", 980, 404, 60, 20),
            _word("BUY", 1100, 402, 70, 24),
        ]
        rows = parse_shop_rows(words, FRAME)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].attack, 3)
        self.assertIsNone(rows[0].defense)
        self.assertEqual(rows[0].owned, 1)
        self.assertEqual(rows[0].rarity, "COMMON WEAPON")
        self.assertEqual(rows[0].slot, "Weapons")
        self.assertEqual(
            format_shop_stats(rows[0]),
            "COMMON WEAPON  ·  +3 Attack  ·  Owned 1  ·  $500",
        )
        armor = [
            "UNCOMMON ARMOR",
            "Butcher's Chain Apron",
            "+1 Attack +4 Defense",
            "Owned: 2",
            "$5,000",
            "BUY",
        ]
        harvested = harvest_shop_from_words(armor)
        self.assertEqual(len(harvested), 1)
        self.assertEqual(harvested[0].attack, 1)
        self.assertEqual(harvested[0].defense, 4)
        self.assertEqual(harvested[0].slot, "Armor")
        self.assertIn("+1 Attack", format_shop_stats(harvested[0]))
        self.assertIn("+4 Defense", format_shop_stats(harvested[0]))

    def test_buy_word_is_not_a_billion_suffix(self):
        words = [
            _word("Rusty Getaway Sedan", 360, 400, 180, 22),
            _word("$5,000", 980, 404, 70, 20),
            _word("BUY", 1100, 402, 70, 24),
        ]
        rows = parse_shop_rows(words, FRAME)
        self.assertEqual(rows[0].cash, 5000)

    def test_owned_and_tab_strip_are_not_items(self):
        from app.core.shop import is_shop_title
        self.assertFalse(is_shop_title("Owned: 0"))
        self.assertFalse(is_shop_title("ALL WEAPONS ARMOR VEHICLES"))
        self.assertFalse(is_shop_title("COMMON WEAPON"))
        self.assertTrue(is_shop_title("Switch Stiletto"))
        self.assertTrue(is_shop_title("Chamber Guard Halberd"))
        self.assertFalse(is_shop_title("VIP chat tag, +10% cash earned, +10% max energy"))
        self.assertFalse(is_shop_title("Extra Operations Slot"))
        self.assertFalse(is_shop_title("Faster Energy Regen"))
        self.assertFalse(is_shop_title("X OPERATIONS"))
        self.assertFalse(is_shop_title("X FIGHT"))
        self.assertFalse(is_shop_title("Better Henchmen"))
        self.assertFalse(is_shop_title("Jobs pay double cash"))
        self.assertFalse(is_shop_title("Run one more operation at once"))

    def test_robux_shop_is_not_cash_equipment(self):
        from app.core.shop import harvest_shop_from_words, parse_money
        self.assertEqual(parse_money("R$ 220")[1], None)
        self.assertEqual(parse_money("$500")[1], 500)
        words = [
            _word("VIP chat tag", 1400, 400, 160, 22),
            _word("R$ 220", 1500, 404, 70, 20),
            _word("BUY", 1770, 402, 70, 24),
        ]
        self.assertEqual(parse_shop_rows(words, FRAME), [])
        harvested = harvest_shop_from_words([
            "ALL GAME PASSES", "VIP", "VIP chat tag", "R$ 220", "BUY",
        ])
        self.assertEqual(harvested, [])

    def test_stock_timer(self):
        from app.core.shop import parse_stock_timer
        self.assertEqual(parse_stock_timer(["NEW STOCK IN 4:47"]), 4 * 60 + 47)
        self.assertEqual(parse_stock_timer(["NEW STOCK IN 0:30"]), 30)

    def test_gold_priced_row_is_marked_gold(self):
        words = [
            _word("Gold Knuckles", 360, 400, 160, 22),
            _word("GOLD BARS", 980, 404, 100, 20),
            _word("BUY", 1100, 402, 70, 24),
        ]
        rows = parse_shop_rows(words, FRAME)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].gold)
        payload = shop_catalog_payload(rows)
        self.assertEqual(payload["item_count"], 0)

    def test_title_and_buy_parse_without_a_dollar(self):
        words = [
            _word("Blackout Coupe", 360, 400, 160, 22),
            _word("BUY", 1100, 402, 70, 24),
        ]
        rows = parse_shop_rows(words, FRAME)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Blackout Coupe")
        self.assertIsNone(rows[0].cash)
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        self.assertIsNone(find_cash_buy_button(frame, 400, 22))

    def test_green_price_is_not_the_buy_button(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        _paint_buy(frame, 980, 410, hue=50)
        cx, cy = _paint_buy(frame, 1180, 410, hue=22)
        found = find_cash_buy_button(frame, 400, 22)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], cx, delta=8)
        self.assertAlmostEqual(found[1], cy, delta=8)
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        cx, cy = _paint_buy(frame, 1180, 410, hue=22)
        found = find_cash_buy_button(frame, 400, 22)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], cx, delta=8)
        self.assertAlmostEqual(found[1], cy, delta=8)

    def test_only_buys_what_cash_covers(self):
        from app.core.shop import can_afford, catalog_price
        self.assertFalse(can_afford(None, 500))
        self.assertFalse(can_afford(122_000_000, None))
        self.assertFalse(can_afford(122_000_000, 482_000_000))
        self.assertTrue(can_afford(122_000_000, 14_900_000))
        row = type("Row", (), {"name": "Chamber Guard Halberd", "cash": None})()
        catalog = [type("Item", (), {"name": "Chamber Guard Halberd", "cash": 14_900_000})()]
        self.assertEqual(catalog_price(row, catalog), 14_900_000)
        book = Playbook(features={"Shop": True})
        self.assertTrue(book.shop_enabled())
        self.assertEqual(len(book.selected_shop()), 0)

    def test_bank_flags(self):
        book = Playbook(features={"Bank": True})
        book.withdraw_all = True
        book.deposit_all = True
        data = book.to_dict()
        self.assertTrue(data["withdraw_all"])
        self.assertTrue(data["deposit_all"])


    def test_robux_words_on_the_same_row_do_not_hide_cash_stats(self):
        from app.core.shop import format_shop_stats
        words = [
            _word("EPIC WEAPON", 360, 372, 140, 16),
            _word("Chamber Guard Halberd", 360, 400, 200, 22),
            _word("+12 Attack +1 Defense", 360, 426, 160, 16),
            _word("Owned: 0", 360, 448, 80, 16),
            _word("$14.9M", 980, 404, 70, 20),
            _word("BUY", 1100, 402, 70, 24),
            _word("X OPERATIONS", 40, 400, 120, 20),
            _word("VIP chat tag", 1450, 400, 140, 20),
            _word("R$ 220", 1600, 404, 70, 20),
            _word("BUY", 1770, 402, 70, 24),
        ]
        rows = parse_shop_rows(words, FRAME)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Chamber Guard Halberd")
        self.assertEqual(rows[0].rarity, "EPIC WEAPON")
        self.assertEqual(rows[0].attack, 12)
        self.assertEqual(rows[0].defense, 1)
        self.assertEqual(rows[0].owned, 0)
        self.assertEqual(rows[0].cash, 14_900_000)
        self.assertIn("EPIC WEAPON", format_shop_stats(rows[0]))
        self.assertIn("$14.9M", format_shop_stats(rows[0]))

    def test_scan_keeps_shop_row_stats(self):
        from app.core.shop import format_shop_stats, harvest_shop_from_tab_results
        shot = type("TabShot", (), {
            "name": "SHOP/ALL",
            "words": ["X OPERATIONS", "Chamber Guard Halberd"],
            "items": ["X OPERATIONS", "Chamber Guard Halberd"],
            "shop_rows": [{
                "name": "Chamber Guard Halberd",
                "section": "Weapons",
                "cash": 14_900_000,
                "cash_text": "$14.9M",
                "gold": False,
                "rarity": "EPIC WEAPON",
                "slot": "Weapons",
                "attack": 12,
                "defense": 1,
                "owned": 0,
                "level_req": None,
                "locked": False,
            }],
        })()
        rows = harvest_shop_from_tab_results([shot])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Chamber Guard Halberd")
        self.assertEqual(
            format_shop_stats(rows[0]),
            "EPIC WEAPON  ·  +12 Attack  ·  +1 Defense  ·  Owned 0  ·  $14.9M",
        )

    def test_ocr_order_with_buy_before_name_still_gets_stats(self):
        from app.core.shop import format_shop_stats, harvest_shop_from_words
        harvested = harvest_shop_from_words([
            "EPIC WEAPON",
            "$14.9M",
            "BUY",
            "Chamber Guard Halberd",
            "+12 Attack +1 Defense",
            "Owned: 0",
            "X OPERATIONS",
        ])
        self.assertEqual(len(harvested), 1)
        self.assertEqual(harvested[0].name, "Chamber Guard Halberd")
        self.assertEqual(harvested[0].attack, 12)
        self.assertIn("EPIC WEAPON", format_shop_stats(harvested[0]))
        self.assertIn("$14.9M", format_shop_stats(harvested[0]))

    def test_hud_grain_hides_small_spends(self):
        from app.core.shop import cash_hud_grain, has_shop_list_words
        self.assertEqual(cash_hud_grain(292_000_000), 1_000_000)
        self.assertEqual(cash_hud_grain(500), 1)
        self.assertTrue(has_shop_list_words([_word("BUY", 1100, 400)]))
        self.assertTrue(has_shop_list_words([_word("Worn Leather", 360, 400, 140, 22)]))
        self.assertFalse(has_shop_list_words([_word("Owned: 1", 360, 448)]))

    def test_equipment_all_is_left_of_weapons(self):
        from app.core.shop import find_equipment_all
        words = [
            _word("ALL", 360, 260, 50, 20),
            _word("WEAPONS", 430, 260, 90, 20),
            _word("ALL", 1180, 260, 50, 20),
            _word("GAME PASSES", 1240, 260, 110, 20),
        ]
        found = find_equipment_all(words, FRAME)
        self.assertIsNotNone(found)
        self.assertLess(found[0], 500)

    def test_weapons_strip_still_finds_all(self):
        from app.core.shop import find_equipment_all
        words = [_word("WEAPONS", 430, 260, 90, 20), _word("ARMOR", 540, 260, 70, 20)]
        found = find_equipment_all(words, FRAME)
        self.assertIsNotNone(found)
        self.assertLess(found[0], 430)

    def test_all_click_sits_left_of_vehicles(self):
        from app.core.shop import equipment_all_click
        x, y = equipment_all_click(1920, 1009, (700, 280))
        self.assertLess(x, 400)
        self.assertEqual(y, 280)
        fallback = equipment_all_click(1920, 1009)
        self.assertLess(fallback[0], int(1920 * 0.38))

    def test_small_price_counts_as_bought_when_hud_stays_at_millions(self):
        from app.core.shop_actor import ShopActor
        actor = ShopActor()
        actor._pending = "WORNLEATHER"
        actor._cash_before = 292_000_000
        actor._pending_price = 500
        actor._clicked = {"WORNLEATHER"}
        log = []
        actor._confirm_purchase(292_000_000, log.append)
        self.assertNotIn("WORNLEATHER", actor._clicked)
        actor._pending = "WORNLEATHER"
        actor._cash_before = 292_000_000
        actor._pending_price = 500
        actor._clicked = {"WORNLEATHER"}
        actor._confirm_purchase(292_000_000, log.append)
        self.assertIn("WORNLEATHER", actor._clicked)
        self.assertTrue(any("cannot show" in line for line in log))

    def test_big_buy_still_needs_cash_to_drop(self):
        from app.core.shop_actor import ShopActor
        actor = ShopActor()
        actor._pending = "WINTERPALACESABER"
        actor._cash_before = 294_000_000
        actor._pending_price = 21_200_000
        actor._clicked = {"WINTERPALACESABER"}
        log = []
        actor._confirm_purchase(294_000_000, log.append)
        self.assertNotIn("WINTERPALACESABER", actor._clicked)
        actor._pending = "WINTERPALACESABER"
        actor._cash_before = 294_000_000
        actor._pending_price = 21_200_000
        actor._clicked = {"WINTERPALACESABER"}
        actor._confirm_purchase(273_000_000, log.append)
        self.assertTrue(any("cash dropped" in line for line in log))

    def test_blank_list_reopens_all_before_finishing(self):
        from app.core.shop_actor import ShopActor
        actor = ShopActor()
        actor._opened = True
        log = []
        for _ in range(5):
            actor._empty_list(log.append)
        self.assertFalse(actor.pass_done)
        self.assertTrue(any("opening ALL" in line for line in log))
        actor._opened = True
        for _ in range(5):
            actor._empty_list(log.append)
        actor._opened = True
        for _ in range(5):
            actor._empty_list(log.append)
        self.assertTrue(actor.pass_done)
        self.assertTrue(any("still not read" in line for line in log))


if __name__ == "__main__":
    unittest.main()
