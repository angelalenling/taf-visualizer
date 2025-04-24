import requests
import re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.image as mpimg


# -------------------------
# Function: Parse TAF times with 24Z fix
# -------------------------
def parse_taf_time(day, hour, base_year, base_month):
    if hour == 24:
        hour = 0
        dt = datetime(base_year, base_month, day, tzinfo=timezone.utc) + timedelta(days=1)
        return dt.replace(hour=hour)
    return datetime(base_year, base_month, day, hour, tzinfo=timezone.utc)

# -------------------------
# STEP 1: Get TAF from NWS
# -------------------------
url = "https://forecast.weather.gov/product.php?site=MPX&product=TAF&issuedby=MSP"
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")
taf_text = soup.find("pre").get_text().strip()
print("Raw TAF:\n", taf_text)

# -------------------------
# STEP 2: Extract valid time period
# -------------------------
valid_period = re.search(r'\b(\d{4})/(\d{4})\b', taf_text)
start_day, start_hour = int(valid_period[1][:2]), int(valid_period[1][2:])
end_day, end_hour = int(valid_period[2][:2]), int(valid_period[2][2:])
now = datetime.now(timezone.utc)
base_year, base_month = now.year, now.month
start_time = parse_taf_time(start_day, start_hour, base_year, base_month)
end_time = parse_taf_time(end_day, end_hour, base_year, base_month)

# -------------------------
# STEP 3: Segment into FM blocks
# -------------------------
fm_matches = list(re.finditer(r'\bFM(\d{6})\b', taf_text))
time_blocks = []

# Work forward through FM segments
for i, match in enumerate(fm_matches):
    fm_str = match.group(1)
    seg_start = parse_taf_time(int(fm_str[:2]), int(fm_str[2:4]), base_year, base_month)
    seg_text_start = match.end()
    seg_text_end = fm_matches[i + 1].start() if i + 1 < len(fm_matches) else len(taf_text)
    seg_text = taf_text[seg_text_start:seg_text_end].strip()
    seg_end = (
        parse_taf_time(int(fm_matches[i + 1].group(1)[:2]), int(fm_matches[i + 1].group(1)[2:4]), base_year, base_month)
        if i + 1 < len(fm_matches) else end_time
    )
    time_blocks.append((seg_start, seg_end, seg_text))

tempo_matches = list(re.finditer(r'TEMPO (\d{4})/(\d{4}) (.+?)(?=(TEMPO|\bFM|\Z))', taf_text, re.DOTALL))
tempo_blocks = []

for match in tempo_matches:
    tempo_start_day = int(match.group(1)[:2])
    tempo_start_hour = int(match.group(1)[2:])
    tempo_end_day = int(match.group(2)[:2])
    tempo_end_hour = int(match.group(2)[2:])

    tempo_start = parse_taf_time(tempo_start_day, tempo_start_hour, base_year, base_month)
    tempo_end = parse_taf_time(tempo_end_day, tempo_end_hour, base_year, base_month)
    tempo_text = match.group(3).strip()

    tempo_blocks.append((tempo_start, tempo_end, tempo_text))


# Insert initial conditions (before first FM)
initial_end = fm_matches[0].start() if fm_matches else len(taf_text)
initial_conditions = taf_text[:initial_end].strip()
first_fm_time = time_blocks[0][0] if time_blocks else end_time
time_blocks.insert(0, (start_time, first_fm_time, initial_conditions))

# -------------------------
# STEP 4: Cloud icons & output
# -------------------------


weather_images = {
    "TSRA": mpimg.imread("Wx_images/tsra.png"),
    "TS": mpimg.imread("Wx_images/tsra.png"),
    "VCTS": mpimg.imread("Wx_images/vcts.png"),
    "RA": mpimg.imread("Wx_images/rain.png"),
    "SHRA": mpimg.imread("Wx_images/rain.png"),
    "SN": mpimg.imread("Wx_images/snow.png"),
    "FZRA": mpimg.imread("Wx_images/freezing_rain.png"),
}


segments = []
for seg_start, seg_end, seg_text in time_blocks:
    clouds = re.findall(r'(FEW|SCT|BKN|OVC)(\d{3})', seg_text)
    wx_codes = re.findall(r'\b(?:TSRA|VCTS|SHRA|RA|TS|SN|FZRA|BR|FG)\b', seg_text)

    if clouds:
        clouds_ft = [(cov, int(alt) * 100) for cov, alt in clouds]
        wx_codes = re.findall(r'\b(?:TSRA|VCTS|SHRA|RA|TS|SN|FZRA|BR|FG)\b', seg_text)
    else:
        clouds_ft = []
    
    segments.append((seg_start, seg_end, clouds_ft, wx_codes, seg_text))



# STEP 2: Load cloud images
few_cloud = mpimg.imread("Wx_images/few.png")
sct_cloud = mpimg.imread("Wx_images/sct.png")
bkn_cloud = mpimg.imread("Wx_images/bkn.png")
cirrus_cloud = mpimg.imread("Wx_images/cirrus.png")
wind = mpimg.imread("Wx_images/wind.png")

# STEP 3: Coverage to cloud count mapping
coverage_density = {
    "FEW": 1,
    "SCT": 2,
    "BKN": 2,
    "OVC": "hourly"  # Special case: every hour
}

# STEP 4: Plot setup
fig, ax = plt.subplots(figsize=(12, 6))

for start, end, clouds, wx_codes, seg_text in segments:
    wind_match = re.search(r'\b(\d{3})(\d{2})(G\d{2})?KT\b', seg_text)
    if wind_match and wind_match.group(3):  # gust exists
        gust = int(wind_match.group(3)[1:])  # remove 'G'
        mid_time = start + (end - start) / 2
        wind_height = 800

        imagebox = OffsetImage(wind, zoom=0.15)
        ab = AnnotationBbox(imagebox, (mdates.date2num(mid_time), wind_height), frameon=False)
        ax.add_artist(ab)
    for cov, height in clouds:
        duration_hours = int((end - start).total_seconds() / 3600)

        if height >= 20000:
            # ---- CIRRUS CLOUDS (stretch across time)
            extent = [
                mdates.date2num(start),
                mdates.date2num(end),
                height - 2000,
                height + 2000
            ]
            ax.imshow(
                cirrus_cloud,
                aspect='auto',
                extent=extent,
                alpha=0.9,  # slight transparency
                zorder=1
            )
        else:
            if cov == 'FEW':
                cloud_img = few_cloud
            elif cov == 'SCT':
                cloud_img = sct_cloud
            elif cov == 'BKN':
                cloud_img = bkn_cloud
            elif cov == 'OVC':
                cloud_img = bkn_cloud
            
            
            if cov == "OVC":
                times = [start + timedelta(hours=i + 0.5) for i in range(duration_hours)]
            else:
                cloud_count = min(coverage_density[cov], duration_hours)
                spacing = duration_hours / (cloud_count + 1)
                times = [start + timedelta(hours=(i + 1) * spacing) for i in range(cloud_count)]

            # Place the cloud icons
            for t in times:
                imagebox = OffsetImage(cloud_img, zoom=0.02)
                ab = AnnotationBbox(imagebox, (mdates.date2num(t), height), frameon=False)
                ax.add_artist(ab)
    for wx in wx_codes:
        if wx == 'BR':
                x_start = mdates.date2num(start)
                x_end = mdates.date2num(end)
                y_base = -5000
                height = min([h for _, h in clouds]) if clouds else 1000
                
                ax.fill_betweenx(
                    [y_base, height],
                    x_start,
                    x_end,
                    color='lightgrey',
                    alpha=0.5,
                    zorder=2
                )
        if wx == 'FG':
                x_start = mdates.date2num(start)
                x_end = mdates.date2num(end)
                y_base = -5000
                height = min([h for _, h in clouds]) if clouds else 1000
                
                ax.fill_betweenx(
                    [y_base, height],
                    x_start,
                    x_end,
                    color='lightgrey',
                    alpha=0.9,
                    zorder=2
                )
                
        elif wx in ['RA', 'TSRA', 'TS','SHRA'] and wx in weather_images:
            weather_img = weather_images[wx]
            duration_hours = int((end - start).total_seconds() / 3600)
            times = [start + timedelta(hours=i + 0.5) for i in range(duration_hours)]
            for t in times:
                if wx in ['TSRA', 'TS']:
                    height = min([h for _, h in clouds]) + 3000
                else:
                    height = min([h for _, h in clouds]) if clouds else 1000
                x = mdates.date2num(t)
                imagebox = OffsetImage(weather_img, zoom=0.3)
                ab = AnnotationBbox(
                    imagebox,
                    (x, height),             
                    frameon=False,
                    box_alignment=(0.5, 1),   
                    zorder=3
                )
                ax.add_artist(ab)

        elif wx in weather_images:
            weather_img = weather_images[wx]
            t = start + (end - start) / 2
            x = mdates.date2num(t)
            y = min([h for _, h in clouds]) - 6500 if clouds else 1000

            imagebox = OffsetImage(weather_img, zoom=.3)
            ab = AnnotationBbox(imagebox, (x, y), frameon=False)
            ax.add_artist(ab)

    for start, end, text in tempo_blocks:
        tempo_clouds = re.findall(r'(FEW|SCT|BKN|OVC)(\d{3})', text)
        tempo_wx = re.findall(r'\b(?:TSRA|VCTS|SHRA|RA|TS|SN|FZRA|BR|FG)\b', text)
        wind_match = re.search(r'\b(\d{3})(\d{2})(G\d{2})?KT\b', text)

        if 'RA' in tempo_wx and 'RA' in weather_images:
            t = start + (end - start) / 2
            y = 1000
            imagebox = OffsetImage(weather_images['RA'], zoom=0.2)
            ab = AnnotationBbox(imagebox, (mdates.date2num(t), y), frameon=False, alpha=0.6)
            ax.add_artist(ab)

        if 'FG' in tempo_wx or 'BR' in tempo_wx:
            x_start = mdates.date2num(start)
            x_end = mdates.date2num(end)
            y_base = -5000
            height = min([int(alt)*100 for _, alt in tempo_clouds]) if tempo_clouds else 1000
            
            if 'BR' in tempo_wx:
                ax.fill_betweenx(
                    [y_base, height],
                    x_start,
                    x_end,
                    color='lightgrey',
                    alpha=0.5,
                    zorder=2
                )
            if 'FG' in tempo_wx:                
                    ax.fill_betweenx(
                        [y_base, height],
                        x_start,
                        x_end,
                        color='lightgrey',
                        alpha=0.9,
                        zorder=2
                    )

        # Plot clouds
        for cov, alt in tempo_clouds:
            height = int(alt) * 100
            mid_time = start + (end - start) / 2
            if cov == 'FEW': cloud_img = few_cloud
            elif cov == 'SCT': cloud_img = sct_cloud
            elif cov == 'BKN': cloud_img = bkn_cloud
            elif cov == 'OVC': cloud_img = bkn_cloud
            else: continue

            imagebox = OffsetImage(cloud_img, zoom=0.02)
            ab = AnnotationBbox(imagebox, (mdates.date2num(mid_time), height), frameon=False, alpha=0.8)
            ax.add_artist(ab)

        # Plot gusting wind icon
        # group(3) is the gust portion (e.g., 'G20' from '26012G20KT'), so [1:] gets just the number '20'
        if wind_match and wind_match.group(3):
            gust = int(wind_match.group(3)[1:])
            if gust:
                mid_time = start + (end - start) / 2
                wind_height = -2000
                imagebox = OffsetImage(wind, zoom=0.2)
                ab = AnnotationBbox(imagebox, (mdates.date2num(mid_time), wind_height), frameon=False)
                ax.add_artist(ab)

# STEP 5: Format plot
import matplotlib.image as mpimg

# Load your JPEG background
bg_img = mpimg.imread("Wx_images/minneapolis.png")  # replace with your filename

# Place it behind everything else
ax.imshow(
    bg_img,
    extent=[
        mdates.date2num(segments[0][0]),  # x start (time)
        mdates.date2num(segments[-1][1]),  # x end (time)
        -5000, 27000  # y extent (altitude)
    ],
    aspect='auto',
    zorder=0  # ensure it's behind clouds
)
ax.set_ylim(-5000, 27000)
ax.set_yticks([1000, 5000, 10000, 15000, 20000, 25000])
ax.set_xlim(mdates.date2num(segments[0][0]), mdates.date2num(segments[-1][1]))

import pytz
central = pytz.timezone("US/Central")
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d %I:%M %p', tz=central))
fig.autofmt_xdate()
ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))

x_start, x_end = ax.get_xlim()
dt_start = mdates.num2date(x_start).astimezone(central)
dt_end = mdates.num2date(x_end).astimezone(central)

# Round down to the nearest hour
current = dt_start.replace(minute=0, second=0, microsecond=0)
if current.minute > 0:
    current += timedelta(hours=1)

ymin = -5000
ymax = 27000

# Shade every hour block from 9PM to 6AM
while current <= dt_end:
    if current.hour >= 21 or current.hour < 6:
        start = mdates.date2num(current)
        end = mdates.date2num(current + timedelta(hours=1))
        ax.fill_betweenx(
            [ymin, ymax],
            start,
            end,
            color='black',
            alpha=0.2,
            zorder = 0,
            edgecolor = 'none'
        )
    current += timedelta(hours=1)


ax.set_ylabel("Altitude (ft)")
ax.set_title("KMSP Forecast")

# Set sky-blue background
ax.set_facecolor("#248ccc")
fig.patch.set_facecolor("#248ccc")

plt.tight_layout()

plt.show()