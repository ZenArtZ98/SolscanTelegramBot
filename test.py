import json
from playwright.async_api import async_playwright
import requests
import re
import asyncio
import time





url = "https://solscan.io/token/26H1zfAqYmMZ3enznFz46fTswZuVR1bDxSTqit2AWZkU"


async def solscan_data(url):
  data = dict()
  async with async_playwright() as p:
    async def handle_response(response):
      # the endpoint we are insterested in
      if ("account?" in response.url):
        items = await response.json()

        metadata = items["data"]["metadata"]["data"]['uri']
        response = requests.get(metadata)
        response_data = response.json()
        data['name'] = response_data['name']
        data['symbol'] = response_data['symbol']
        telegram_link_regular = re.compile(r'(https?:\/\/?t\.me[^\s@]*[a-zA-Z0-9])')
        tg_link = telegram_link_regular.findall(response.text)
        if not tg_link:
          data['tg_link'] = ""
        else:
          data['tg_link'] = tg_link[0]

    browser = await p.chromium.launch()
    page = await browser.new_page()

    page.on("response", handle_response)
    await page.goto(url, wait_until="networkidle")

    await page.context.close()
    await browser.close()

  return data

# xyz = solscan_data(url=url)
time.sleep(15)
xyz = asyncio.run(solscan_data(url=url))
print(xyz)



# tg_link_solscan = xyz['tg_link']
#
# if not tg_link_solscan:
#   pass
# else:
#   print(xyz['name'])



