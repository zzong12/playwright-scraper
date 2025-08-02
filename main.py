from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import HttpUrl
from playwright.async_api import async_playwright
from cachetools import TTLCache
from contextlib import asynccontextmanager
import asyncio
from typing import Optional, Dict, List
import time
import logging

# Unified cache with 1 hour TTL and max 1000 entries
cache = TTLCache(maxsize=1000, ttl=3600)

# Preload configuration 
preload_urls: Dict[str, dict] = {}  # {url: {"last_updated": timestamp, "interval": 600}}

# Concurrency control (max 50 concurrent requests)
semaphore = asyncio.Semaphore(50)

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# TTLCache automatically manages expiration and size limits

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Launch browser at startup
    try:
        playwright = await async_playwright().start()
        browser = await playwright.firefox.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        app.state.browser = browser  # Store browser on app state
        app.state.playwright = playwright
        
        # Start preload task
        asyncio.create_task(preload_task(app))
        
        yield {
            "playwright": playwright,
            "browser": browser
        }
    finally:
        # Cleanup resources with error handling
        try:
            if hasattr(app.state, 'browser'):
                logger.info("Closing browser...")
                await app.state.browser.close()
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
        
        try:
            if hasattr(app.state, 'playwright'):
                logger.info("Stopping playwright...")
                await app.state.playwright.stop()
        except Exception as e:
            logger.error(f"Error stopping playwright: {str(e)}")

async def preload_task(app: FastAPI):
    """Background task to preload URLs"""
    while True:
        try:
            logger.info("Starting preload cycle for %d URLs", len(preload_urls))
            success_count = 0
            for url in list(preload_urls.keys()):
                page = None
                try:
                    browser = app.state.browser
                    page = await browser.new_page()
                    
                    # Disable cache to ensure fresh content
                    await page.route("**/*", lambda route: route.continue_(headers={**route.request.headers, "Cache-Control": "no-cache, no-store, must-revalidate"}))
                    
                    # Universal smart loading strategy for all websites
                    try:
                        await page.goto(url, timeout=45000)
                        # Smart wait: check if content is still changing
                        initial_length = len(await page.content())
                        await page.wait_for_timeout(500)
                        final_length = len(await page.content())
                        # Only wait more if content is still changing
                        if final_length != initial_length:
                            await page.wait_for_timeout(1000)
                    except Exception:
                        # Fallback to load if networkidle times out
                        logger.warning(f"Networkidle timeout for {url}, falling back to load event")
                        await page.goto(url, timeout=30000)
                        await page.wait_for_timeout(1000)
                    content = await page.content()
                    # Check content length
                    if len(content) == 0:
                        logger.warning(f"Preload failed for {url}: Empty content")
                        continue
                    
                    # Store in unified cache
                    cache[url] = content
                    preload_urls[url]["last_updated"] = time.time()
                    success_count += 1
                    logger.info("Successfully preloaded %s (%d bytes)", url, len(content))
                except Exception as e:
                    logger.error(f"Preload failed for {url}: {str(e)}")
                finally:
                    # Always close the page to prevent memory leaks
                    if page:
                        try:
                            await page.close()
                        except Exception as e:
                            logger.error(f"Error closing page for {url}: {str(e)}")
            
            # TTLCache automatically manages size limits
            
            logger.info("Preload cycle completed: %d/%d URLs succeeded",
                      success_count, len(preload_urls))
        except Exception as e:
            logger.error(f"Preload task error: {str(e)}")
        
        await asyncio.sleep(30)  # Sleep for 10 minutes (balanced approach)

app = FastAPI(lifespan=app_lifespan)

@app.get("/preload/list", response_class=JSONResponse)
async def list_preload_urls():
    """List all preload URLs and their status"""
    result = []
    current_time = time.time()
    for url, info in preload_urls.items():
        content = cache.get(url, "")
        result.append({
            "url": url,
            "last_updated": info["last_updated"],
            "content_length": len(content),
            "cache_valid": url in cache  # TTLCache handles expiration automatically
        })
    return result

@app.post("/preload/update")
async def update_preload_urls(urls: List[str]):
    """Update preload URLs configuration"""
    logger.info("Updating preload URLs configuration")
    added = 0
    removed = 0
    
    for url in urls:
        if not url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URL format skipped: {url}")
            continue
        if url not in preload_urls:
            preload_urls[url] = {
                "last_updated": 0,
                "interval": 600
            }
            added += 1
            logger.info(f"Added new preload URL: {url}")
    
    # Remove URLs not in the new list
    for url in list(preload_urls.keys()):
        if url not in urls:
            preload_urls.pop(url, None)
            cache.pop(url, None)  # Remove from unified cache
            removed += 1
            logger.info(f"Removed preload URL: {url}")
    
    logger.info(f"Preload URLs updated: {added} added, {removed} removed, total {len(preload_urls)}")
    return {
        "status": "success",
        "count": len(preload_urls),
        "added": added,
        "removed": removed
    }

@app.get("/scrape", response_class=PlainTextResponse)
async def scrape_url(
    request: Request,
    url: str = Query(..., description="URL to scrape")
):
    # Validate URL format
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    force = request.query_params.get("force", "false").lower() == "true"
    
    # Check unified cache if not forcing
    if not force and url in cache:
        logger.info(f"Returning from cache: {url}")
        return cache[url]

    async with semaphore:  # Concurrency control
        page = None
        try:
            browser = request.app.state.browser
            page = await browser.new_page()
            
            # Disable cache to ensure fresh content
            await page.route("**/*", lambda route: route.continue_(headers={**route.request.headers, "Cache-Control": "no-cache, no-store, must-revalidate", "keep-alive": "false"}))
            
            # Universal smart loading strategy for all websites
            try:
                await page.goto(url, timeout=45000)
                # Smart wait: check if content is still changing
                initial_length = len(await page.content())
                await page.wait_for_timeout(500)
                final_length = len(await page.content())
                # Only wait more if content is still changing
                if final_length != initial_length:
                    await page.wait_for_timeout(1000)
            except Exception:
                # Fallback to load if networkidle times out
                logger.warning(f"Networkidle timeout for {url}, falling back to load event")
                await page.goto(url, timeout=30000)
                await page.wait_for_timeout(1000)
            content = await page.content()

            # Store in unified cache
            cache[url] = content
            
            logger.info(f"Fresh content fetched for: {url} (%d bytes)", len(content))
            return content
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Browser operation failed: {str(e)}")
        finally:
            # Always close the page to prevent memory leaks
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.error(f"Error closing page for {url}: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)