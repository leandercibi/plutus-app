#!/usr/bin/env python3
"""Full functional test - interact with every feature, take screenshots."""

import time
import os
from playwright.sync_api import sync_playwright

DASHBOARD_URL = "http://localhost:8501"
SS = "/Users/leander/personal-projects/plutus-app/screenshots/functional"
os.makedirs(SS, exist_ok=True)


def ss(page, name):
    """Take screenshot with consistent naming."""
    path = f"{SS}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"   📸 {name}.png")
    return path


def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()

        print("🧪 FULL FUNCTIONAL TEST - Every Feature")
        print("=" * 70)

        # Load
        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)
        time.sleep(4)
        ss(page, "01_loaded")

        # ═══════════════════════════════════════════════════════════════
        # HOME TAB
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 🏠 HOME TAB ━━━")
        page.get_by_role("tab", name="🏠 Home").click()
        time.sleep(2)
        ss(page, "02_home")
        print("   ✓ Home tab loaded")

        # ═══════════════════════════════════════════════════════════════
        # WATCHLIST TAB - Add symbols
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 👁 WATCHLIST - Adding symbols ━━━")
        page.get_by_role("tab", name="👁 Watchlist").click()
        time.sleep(2)
        ss(page, "03_watchlist_empty")

        # Add INFY to watchlist
        print("   Adding INFY to watchlist...")
        text_inputs = page.locator("input[type='text']").all()
        for inp in text_inputs:
            if inp.is_visible():
                inp.fill("INFY")
                break
        time.sleep(0.5)
        ss(page, "04_watchlist_typed_infy")

        # Click Add button
        add_btn = page.get_by_role("button", name="Add to watchlist")
        if add_btn.is_visible():
            add_btn.click()
            time.sleep(3)
            ss(page, "05_watchlist_added_infy")
            print("   ✓ Added INFY to watchlist")
        else:
            print("   ⚠️ Add button not found")

        # Add TCS
        print("   Adding TCS to watchlist...")
        page.get_by_role("tab", name="👁 Watchlist").click()
        time.sleep(2)
        text_inputs = page.locator("input[type='text']").all()
        for inp in text_inputs:
            if inp.is_visible():
                inp.fill("TCS")
                break
        time.sleep(0.5)

        add_btn = page.get_by_role("button", name="Add to watchlist")
        if add_btn.is_visible():
            add_btn.click()
            time.sleep(3)
            ss(page, "06_watchlist_added_tcs")
            print("   ✓ Added TCS to watchlist")

        # Final watchlist state
        time.sleep(2)
        ss(page, "07_watchlist_final")
        print("   ✓ Watchlist with symbols")

        # ═══════════════════════════════════════════════════════════════
        # PORTFOLIO TAB - View portfolio, test Check button
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 💼 PORTFOLIO - Testing interactions ━━━")
        page.get_by_role("tab", name="💼 Portfolio").click()
        time.sleep(2)
        ss(page, "08_portfolio_initial")
        print("   ✓ Portfolio tab loaded")

        # Check if portfolio selector is visible
        content = page.content()
        if "test-local" in content:
            print("   ✓ Portfolio 'test-local' visible in selector")

        # Look for Check button and click it
        check_btns = page.get_by_role("button").all()
        for btn in check_btns:
            try:
                text = btn.inner_text()
                if "check" in text.lower() or "pre-trade" in text.lower():
                    print(f"   Clicking button: '{text}'")
                    btn.click()
                    time.sleep(2)
                    ss(page, "09_portfolio_check_clicked")
                    print("   ✓ Check button clicked")
                    break
            except:
                pass

        # Look for Buy section
        buy_btns = page.get_by_role("button").all()
        for btn in buy_btns:
            try:
                text = btn.inner_text()
                if "buy" in text.lower():
                    print(f"   Found Buy button: '{text}'")
                    break
            except:
                pass

        ss(page, "10_portfolio_full")

        # ═══════════════════════════════════════════════════════════════
        # STRATEGY LAB - Run backtest
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 🧪 STRATEGY LAB - Running backtest ━━━")
        page.get_by_role("tab", name="🧪 Strategy Lab").click()
        time.sleep(2)
        ss(page, "11_strategy_lab_initial")

        # Find the symbol input and enter INFY
        text_inputs = page.locator("input[type='text']").all()
        for inp in text_inputs:
            try:
                if inp.is_visible() and inp.input_value() in ["RELIANCE", ""]:
                    inp.fill("INFY")
                    print("   ✓ Entered INFY for backtest")
                    break
            except:
                pass

        time.sleep(0.5)
        ss(page, "12_strategy_lab_symbol_entered")

        # Click Run button
        run_btn = page.get_by_role("button", name="Run")
        if run_btn.is_visible():
            print("   Clicking Run backtest...")
            run_btn.click()
            time.sleep(10)  # Wait for backtest to complete
            ss(page, "13_strategy_lab_result")
            print("   ✓ Backtest executed")
        else:
            # Try other button names
            btns = page.get_by_role("button").all()
            for btn in btns:
                try:
                    text = btn.inner_text()
                    if "run" in text.lower() or "backtest" in text.lower():
                        print(f"   Clicking: '{text}'")
                        btn.click()
                        time.sleep(10)
                        ss(page, "13_strategy_lab_result")
                        print("   ✓ Backtest executed")
                        break
                except:
                    pass

        # ═══════════════════════════════════════════════════════════════
        # SIGNALS TAB - Analyze stock
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 📊 SIGNALS - Testing Analyze ━━━")
        page.get_by_role("tab", name="📊 Signals").click()
        time.sleep(2)
        ss(page, "14_signals_initial")

        # Find symbol input
        text_inputs = page.locator("input[type='text']").all()
        for inp in text_inputs:
            try:
                if inp.is_visible():
                    inp.fill("INFY")
                    print("   ✓ Entered INFY for analysis")
                    break
            except:
                pass

        time.sleep(0.5)
        ss(page, "15_signals_symbol_entered")
        print("   ⚠️ Skipping Analyze click (requires OpenRouter API key + 30s wait)")

        # ═══════════════════════════════════════════════════════════════
        # NEWS FEED TAB
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 📰 NEWS FEED ━━━")
        page.get_by_role("tab", name="📰 News Feed").click()
        time.sleep(2)
        ss(page, "16_news_feed")
        print("   ✓ News feed tab loaded")

        # ═══════════════════════════════════════════════════════════════
        # HISTORY TAB
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ 📋 HISTORY ━━━")
        page.get_by_role("tab", name="📋 History").click()
        time.sleep(2)
        ss(page, "17_history")
        print("   ✓ History tab loaded")

        # ═══════════════════════════════════════════════════════════════
        # SETTINGS TAB
        # ═══════════════════════════════════════════════════════════════
        print("\n━━━ ⚙️ SETTINGS ━━━")
        page.get_by_role("tab", name="⚙️ Settings").click()
        time.sleep(2)
        ss(page, "18_settings")
        print("   ✓ Settings tab loaded")

        # Check secrets are redacted
        content = page.content()
        if "***" in content:
            print("   ✓ Secrets redacted")
        if "API_PORT" in content:
            print("   ✓ Config keys visible")

        # ═══════════════════════════════════════════════════════════════
        # FINAL SUMMARY
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("📊 TEST RESULTS")
        print("=" * 70)

        screenshots = sorted([f for f in os.listdir(SS) if f.endswith(".png")])
        print(f"\n📸 {len(screenshots)} screenshots captured:")
        for s in screenshots:
            print(f"   • {s}")

        # Check for errors
        print("\n🔍 Error check:")
        content = page.content()
        errors = []
        if "TypeError" in content:
            errors.append("TypeError found")
        if "ImportError" in content:
            errors.append("ImportError found")
        if "NameError" in content:
            errors.append("NameError found")

        if errors:
            print(f"   ❌ Errors: {', '.join(errors)}")
        else:
            print("   ✓ No Python errors visible in UI")

        time.sleep(3)
        browser.close()

        print(f"\n✅ All screenshots saved to: {SS}/")


if __name__ == "__main__":
    test()
