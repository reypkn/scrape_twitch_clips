import os
import requests
import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# Twitch API credentials (replace with your own)
CLIENT_ID = "n8jflzhuunlwt942q5rkz4opcnng1o"
CLIENT_SECRET = "p8f0wmf717y6te0vlkt9ow4jg9wsxd"
BASE_URL = "https://api.twitch.tv/helix"

# Folder to save downloaded clips
DOWNLOAD_FOLDER = os.path.expanduser("~/Downloads/twitch_clips")

# File containing channel names (one per line)
CHANNEL_LIST_FILE = "channels.txt"

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
        raise ValueError(f"Channel '{channel_name}' not found")

# Step 3: Fetch clips from the last 7 days for a broadcaster
def fetch_clips_last_7_days(broadcaster_id, token):
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }
    url = f"{BASE_URL}/clips"
    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"  # ISO 8601 format
    params = {
        "broadcaster_id": broadcaster_id,
        "started_at": seven_days_ago,
        "first": 100  # Fetch 100 clips in one request (Twitch API limit)
    }
    clips = []
    while True:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()["data"]
        if not data:
            break
        clips.extend(data)
        # Check for pagination
        pagination = response.json().get("pagination", {}).get("cursor")
        if not pagination:
            break
        params["after"] = pagination
    return clips

# Step 4: Use Playwright to download the clip
async def download_clip_with_playwright(clip_url, clip_name, save_path):
    async with async_playwright() as p:
        # Launch the browser
        browser = await p.chromium.launch(headless=True)  # Set headless=True to hide the browser
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

        # Sanitize the clip name to create a valid filename
        sanitized_clip_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in clip_name)
        clip_name_with_extension = f"{sanitized_clip_name}.mp4"
        save_file_path = os.path.join(save_path, clip_name_with_extension)

        # Correct usage of expect_download on the Page object
        print(f"Downloading clip: {clip_name_with_extension}")
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value
        await download.save_as(save_file_path)

        print(f"Downloaded: {save_file_path}")

        # Close the browser
        await browser.close()

# Read channel names from a file
def read_channels_from_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Channel list file '{file_path}' not found!")
    with open(file_path, "r") as file:
        channels = [line.strip() for line in file.readlines() if line.strip()]
    return channels

# Main function
async def main():
    # Read channel names from the text file
    try:
        channels = read_channels_from_file(CHANNEL_LIST_FILE)
    except FileNotFoundError as e:
        print(e)
        return

    # Ensure the download folder exists
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    # Step 1: Get authentication token
    print("Authenticating with Twitch API...")
    token = get_oauth_token(CLIENT_ID, CLIENT_SECRET)

    # Process each channel
    for channel_name in channels:
        print(f"\nProcessing channel: {channel_name}")
        try:
            # Step 2: Get broadcaster ID
            print(f"Retrieving broadcaster ID for channel: {channel_name}")
            broadcaster_id = get_broadcaster_id(channel_name, token)

            # Step 3: Fetch clips from the last 7 days
            print(f"Fetching clips from the last 7 days for channel: {channel_name}")
            clips = fetch_clips_last_7_days(broadcaster_id, token)

            if not clips:
                print(f"No clips found for channel: {channel_name} in the last 7 days.")
                continue

            # Step 4: Download each clip using Playwright
            for clip in clips:
                clip_url = clip["url"]
                clip_name = f"{channel_name}_{clip['title']}"  # Include channel name in the filename
                try:
                    await download_clip_with_playwright(clip_url, clip_name, DOWNLOAD_FOLDER)
                except Exception as e:
                    print(f"Failed to download clip from {clip_url}: {e}")

        except Exception as e:
            print(f"Error processing channel '{channel_name}': {e}")

if __name__ == "__main__":
    asyncio.run(main())