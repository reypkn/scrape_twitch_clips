import os
import requests
import asyncio
from playwright.async_api import async_playwright

# Twitch API credentials (replace with your own)
CLIENT_ID = "n8jflzhuunlwt942q5rkz4opcnng1o"
CLIENT_SECRET = "p8f0wmf717y6te0vlkt9ow4jg9wsxd"
BASE_URL = "https://api.twitch.tv/helix"

# Folder to save downloaded clips
DOWNLOAD_FOLDER = os.path.expanduser("~/Downloads/twitch_clips")


# Step 1: Get OAuth token
def get_oauth_token(client_id, client_secret):
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()["access_token"]


# Step 2: Get broadcaster ID from channel name
def get_broadcaster_id(channel_name, token):
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }
    url = f"{BASE_URL}/users"
    params = {"login": channel_name}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()["data"]
    if data:
        return data[0]["id"]
    else:
        raise ValueError("Channel not found")


# Step 3: Fetch clips from a broadcaster
def fetch_clips(broadcaster_id, token, limit=10):
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }
    url = f"{BASE_URL}/clips"
    params = {"broadcaster_id": broadcaster_id, "first": limit}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()["data"]


# Step 4: Use Playwright to download the clip
async def download_clip_with_playwright(clip_url, save_path):
    async with async_playwright() as p:
        # Launch the browser
        browser = await p.chromium.launch(headless=False)  # Set headless=True if you don't want the browser to open
        context = await browser.new_context()

        # Open a new page and navigate to the clip URL
        page = await context.new_page()
        print(f"Opening clip URL: {clip_url}")
        await page.goto(clip_url)

        # Wait for the "Share" button and click it
        await page.wait_for_selector('button:has-text("Share")', timeout=10000)
        await page.click('button:has-text("Share")')

        # Wait for the "Download Landscape Version" button
        download_button = await page.wait_for_selector('a:has-text("Download Landscape Version")', timeout=10000)

        # Get the download link
        download_link = await download_button.get_attribute("href")
        if not download_link:
            print(f"Could not find download link for {clip_url}")
            await browser.close()
            return

        # Download the video
        clip_name = os.path.basename(download_link.split("?")[0])
        save_file_path = os.path.join(save_path, clip_name)

        # Correct usage of expect_download on the Page object
        print(f"Downloading clip: {clip_name}")
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value
        await download.save_as(save_file_path)

        print(f"Downloaded: {save_file_path}")

        # Close the browser
        await browser.close()


# Main function
async def main():
    # Ask for the channel name
    channel_name = input("Enter the Twitch channel name: ").strip()

    # Ask for the number of clips to download
    try:
        limit = int(input("Enter the number of clips to download (default is 10): ").strip() or 10)
    except ValueError:
        print("Invalid number, defaulting to 10 clips.")
        limit = 10

    # Ensure the download folder exists
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    # Step 1: Get authentication token
    print("Authenticating with Twitch API...")
    token = get_oauth_token(CLIENT_ID, CLIENT_SECRET)

    # Step 2: Get broadcaster ID
    print(f"Retrieving broadcaster ID for channel: {channel_name}")
    broadcaster_id = get_broadcaster_id(channel_name, token)

    # Step 3: Fetch clips
    print(f"Fetching the top {limit} clips for channel: {channel_name}")
    clips = fetch_clips(broadcaster_id, token, limit)

    if not clips:
        print("No clips found!")
        return

    # Step 4: Download each clip using Playwright
    for clip in clips:
        clip_url = clip["url"]
        try:
            await download_clip_with_playwright(clip_url, DOWNLOAD_FOLDER)
        except Exception as e:
            print(f"Failed to download clip from {clip_url}: {e}")


if __name__ == "__main__":
    asyncio.run(main())