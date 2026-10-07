import asyncio, sys
from playwright.async_api import async_playwright
BASE="http://127.0.0.1:8984"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1440,"height":1050})
        errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        for name,link in [("01_fresh_dashboard","Dashboard"),
                          ("02_fresh_trust","数据可信度"),
                          ("03_fresh_phases","周期化"),
                          ("04_fresh_activities","训练"),
                          ("05_fresh_trends","趋势")]:
            try:
                await pg.goto(BASE+"/training", wait_until="load", timeout=30000)
                await pg.wait_for_timeout(4000)
                await pg.get_by_role("link", name=link, exact=True).first.click(timeout=9000)
                await pg.wait_for_timeout(7000)
                await pg.screenshot(path=f"/workspace/cycling-coach/shots5/{name}.png")
                t=await pg.inner_text("body")
                flags=[]
                for kw in ("250W","unknown","null","NaN","undefined","[object"):
                    if kw in t: flags.append(kw)
                print(f"OK {name:<24} 可疑词: {flags or '无'}")
            except Exception as e:
                print(f"FAIL {name:<24} {type(e).__name__}: {str(e)[:50]}")
        if errs: print("JS 错误:", errs[:3])
        await b.close()
asyncio.run(main())
