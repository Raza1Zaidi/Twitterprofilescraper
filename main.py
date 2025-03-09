import asyncio
import json
import random
import gzip
import csv
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from playwright.async_api import async_playwright

app = FastAPI()
templates = Jinja2Templates(directory="templates")

async def init_browser():
    """Initialize a headless Chromium browser using Playwright."""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--window-size=1920,1080"]
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/115.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    page = await context.new_page()
    return playwright, browser, context, page

async def fetch_profile_metrics(page, screen_name, captured_responses):
    """
    Navigate to the Twitter profile page and wait for the GraphQL request containing 
    "UserByScreenName". Then process the response to extract metrics.
    """
    url = f"https://x.com/{screen_name}"
    print(f"\nNavigating to {url}")
    
    # Clear any previously captured responses
    captured_responses.clear()
    
    # Attach an event handler to capture responses
    page.on("response", lambda response: captured_responses.append(response))
    
    # Navigate to the profile URL
    await page.goto(url)
    
    # Wait for page and XHR requests to load
    await asyncio.sleep(random.uniform(3, 9))
    
    # Look for the target response
    target_response = None
    for response in captured_responses:
        req_url = response.request.url
        if "UserByScreenName" in req_url and screen_name.lower() in req_url.lower():
            target_response = response
            break

    if target_response:
        try:
            raw_body = await target_response.body()
            try:
                # Try decoding as utf-8
                body = raw_body.decode("utf-8")
            except Exception:
                # If decoding fails, decompress using gzip then decode
                body = gzip.decompress(raw_body).decode("utf-8")
            data = json.loads(body)
            
            # Attempt both possible locations for metrics
            legacy = data.get("data", {}).get("user", {}).get("result", {}).get("legacy", {})
            if not legacy:
                legacy = data.get("data", {}).get("user", {}).get("legacy", {})
            
            metrics = {
                "followers_count": legacy.get("followers_count"),
                "friends_count": legacy.get("friends_count"),
                "listed_count": legacy.get("listed_count"),
                "location": legacy.get("location")
            }
            print(f"Metrics for {screen_name}: {metrics}")
            return metrics
        except Exception as e:
            print(f"Error parsing response for {screen_name}: {e}")
            return {"error": f"Parsing error: {e}"}
    else:
        print(f"No matching network request found for {screen_name}")
        return {"error": "No matching network request found"}

@app.get("/", response_class=HTMLResponse)
async def read_form(request: Request):
    """Serve the HTML form."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/scrape", response_class=JSONResponse)
async def scrape(
    auth_token: str = Form(...),
    ct0: str = Form(...),
    screen_names: str = Form(...)
):
    """Handle form submission, perform scraping, and return JSON results."""
    # Process comma-separated profiles
    profiles = [name.strip() for name in screen_names.split(",") if name.strip()]

    playwright_obj, browser, context, page = await init_browser()
    
    # Visit the base URL to enable cookie injection (domain must match)
    await page.goto("https://x.com")
    await asyncio.sleep(3)
    
    # Inject cookies into the context
    await context.add_cookies([
        {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
        {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"}
    ])
    
    results = {}
    captured_responses = []
    
    # Iterate through profiles and scrape data
    for profile in profiles:
        captured_responses.clear()
        metrics = await fetch_profile_metrics(page, profile, captured_responses)
        results[profile] = metrics
        await asyncio.sleep(random.uniform(5, 10))
    
    await browser.close()
    await playwright_obj.stop()
    
    # Optionally: Save results as CSV (if needed)
    csv_filename = "results.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
        import csv
        writer = csv.writer(csvfile)
        writer.writerow(["screen_name", "followers_count", "friends_count", "listed_count", "location"])
        for profile, metrics in results.items():
            writer.writerow([
                profile,
                metrics.get("followers_count", ""),
                metrics.get("friends_count", ""),
                metrics.get("listed_count", ""),
                metrics.get("location", "")
            ])
    print(f"CSV file saved as {csv_filename}")
    
    return results
