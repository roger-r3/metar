#!/usr/bin/env python3

import urllib.request
import xml.etree.ElementTree as ET
import board
import neopixel
import time
import datetime
try:
    import astral
except ImportError:
    astral = None
try:
    import displaymetar
except ImportError:
    displaymetar = None

# ---------------------------------------------------------------------------
# ----------- SAFE HELPERS --------------------------------------------------
# ---------------------------------------------------------------------------
def safe_text(element, default=""):
    """Return element.text if it exists and is not None, else default."""
    if element is not None and element.text is not None:
        return element.text
    return default

def safe_int(element, default=0):
    """Return int from element.text if possible, else default."""
    try:
        return int(round(float(safe_text(element, str(default)))))
    except (ValueError, TypeError):
        return default

def safe_float(element, default=0.0):
    """Return float from element.text if possible, else default."""
    try:
        return float(safe_text(element, str(default)))
    except (ValueError, TypeError):
        return default

# ---------------------------------------------------------------------------
# -------------------- START OF CONFIGURATION -------------------------------
# ---------------------------------------------------------------------------

# NeoPixel LED Configuration
LED_COUNT       = 30            # Number of LED pixels.
LED_PIN         = board.D18     # GPIO pin connected to the pixels (18 is PCM).
LED_BRIGHTNESS  = 0.5           # Float from 0.0 (min) to 1.0 (max)
LED_ORDER       = neopixel.GRB  # Strip type and colour ordering

COLOR_VFR       = (255,0,0)     # (original mapping preserved)
COLOR_VFR_FADE  = (125,0,0)
COLOR_MVFR      = (0,0,255)
COLOR_MVFR_FADE = (0,0,125)
COLOR_IFR       = (0,255,0)
COLOR_IFR_FADE  = (0,125,0)
COLOR_LIFR      = (0,125,125)
COLOR_LIFR_FADE = (0,75,75)
COLOR_CLEAR     = (0,0,0)
COLOR_LIGHTNING = (255,255,255)
COLOR_HIGH_WINDS = (255,255,0)

# NEW: color for missing/none
COLOR_NONE = (64, 64, 64)   # Dim gray for "NONE" (no METAR)

# ----- Blink/Fade functionality for Wind and Lightning -----
ACTIVATE_WINDCONDITION_ANIMATION = True
ACTIVATE_LIGHTNING_ANIMATION = True
FADE_INSTEAD_OF_BLINK = True
WIND_BLINK_THRESHOLD = 15
HIGH_WINDS_THRESHOLD = 25
ALWAYS_BLINK_FOR_GUSTS = False
BLINK_SPEED = 1.0
BLINK_TOTALTIME_SECONDS = 300

# ----- Daytime dimming of LEDs based on time of day or Sunrise/Sunset -----
ACTIVATE_DAYTIME_DIMMING = False
BRIGHT_TIME_START = datetime.time(7,0)
DIM_TIME_START = datetime.time(19,0)
LED_BRIGHTNESS_DIM = 0.1
USE_SUNRISE_SUNSET = True
LOCATION = "Seattle"

# ----- External Display support -----
ACTIVATE_EXTERNAL_METAR_DISPLAY = False
DISPLAY_ROTATION_SPEED = 5.0

# ----- Show legend -----
SHOW_LEGEND = True
OFFSET_LEGEND_BY = 0

# ---------------------------------------------------------------------------
# --------------------- END OF CONFIGURATION --------------------------------
# ---------------------------------------------------------------------------

print("Running metar.py at " + datetime.datetime.now().strftime('%d/%m/%Y %H:%M'))

# Sunrise/sunset if astral present
if astral is not None and USE_SUNRISE_SUNSET:
    try:
        ast = astral.Astral()
        try:
            city = ast[LOCATION]
        except KeyError:
            print("Error: Location not recognized, please check list of supported cities and reconfigure")
        else:
            print(city)
            sun = city.sun(date = datetime.datetime.now().date(), local = True)
            BRIGHT_TIME_START = sun['sunrise'].time()
            DIM_TIME_START = sun['sunset'].time()
    except AttributeError:
        import astral.geocoder
        import astral.sun
        try:
            city = astral.geocoder.lookup(LOCATION, astral.geocoder.database())
        except KeyError:
            print("Error: Location not recognized, please check list of supported cities and reconfigure")
        else:
            print(city)
            sun = astral.sun.sun(city.observer, date = datetime.datetime.now().date(), tzinfo=city.timezone)
            BRIGHT_TIME_START = sun['sunrise'].time()
            DIM_TIME_START = sun['sunset'].time()
    print("Sunrise:" + BRIGHT_TIME_START.strftime('%H:%M') + " Sunset:" + DIM_TIME_START.strftime('%H:%M'))

# Initialize the LED strip
bright = BRIGHT_TIME_START < datetime.datetime.now().time() < DIM_TIME_START
print("Wind animation:" + str(ACTIVATE_WINDCONDITION_ANIMATION))
print("Lightning animation:" + str(ACTIVATE_LIGHTNING_ANIMATION))
print("Daytime Dimming:" + str(ACTIVATE_DAYTIME_DIMMING) + (" using Sunrise/Sunset" if USE_SUNRISE_SUNSET and ACTIVATE_DAYTIME_DIMMING else ""))
print("External Display:" + str(ACTIVATE_EXTERNAL_METAR_DISPLAY))
pixels = neopixel.NeoPixel(LED_PIN, LED_COUNT, brightness = LED_BRIGHTNESS_DIM if (ACTIVATE_DAYTIME_DIMMING and bright == False) else LED_BRIGHTNESS, pixel_order = LED_ORDER, auto_write = False)

# Read airports file (same as original, update path if needed)
with open("/home/pi/metar/airports") as f:
    airports = f.readlines()
airports = [x.strip() for x in airports]

try:
    with open("/home/pi/metar/displayairports") as f2:
        displayairports = f2.readlines()
    displayairports = [x.strip() for x in displayairports]
    print("Using subset airports for LED display")
except IOError:
    print("Rotating through all airports on LED display")
    displayairports = None

if len(airports) > LED_COUNT:
    print()
    print("WARNING: Too many airports in airports file, please increase LED_COUNT or reduce the number of airports")
    print("Airports: " + str(len(airports)) + " LED_COUNT: " + str(LED_COUNT))
    print()
    quit()

# Build URL and fetch METARs (same query as before)
url = "https://aviationweather.gov/api/data/metar?ids=" + ",".join([item for item in airports if item != "NULL"]) + "&hoursBeforeNow=5&format=xml&mostRecent=true&mostRecentForEachStation=constraint"
print(url)
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible)'})
content = urllib.request.urlopen(req).read()

# Parse METARs into conditionDict
root = ET.fromstring(content)
conditionDict = {}
stationList = []

for metar in root.iter('METAR'):
    stationId = safe_text(metar.find('station_id'), "UNKNOWN")
    flightCategory = safe_text(metar.find('flight_category'), "NONE")

    windDir = safe_text(metar.find('wind_dir_degrees'), "")
    windSpeed = safe_int(metar.find('wind_speed_kt'), 0)
    windGustSpeed = safe_int(metar.find('wind_gust_kt'), 0)
    # Determine if gusts should be considered a "blink"
    windGust = True if (ALWAYS_BLINK_FOR_GUSTS or windGustSpeed > WIND_BLINK_THRESHOLD) else False

    tempC = safe_int(metar.find('temp_c'), 0)
    dewpointC = safe_int(metar.find('dewpoint_c'), 0)

    vis = 0
    if metar.find('visibility_statute_mi') is not None:
        vis_str = safe_text(metar.find('visibility_statute_mi'), "0")
        vis_str = vis_str.replace('+','')
        try:
            vis = int(round(float(vis_str)))
        except Exception:
            vis = 0

    altimHg = round(safe_float(metar.find('altim_in_hg'), 0.0), 2)
    obs = safe_text(metar.find('wx_string'), "")
    obsTime = datetime.datetime.now()
    if metar.find('observation_time') is not None:
        try:
            obsTime = datetime.datetime.fromisoformat(safe_text(metar.find('observation_time')).replace("Z","+00:00"))
        except Exception:
            pass

    skyConditions = []
    for skyIter in metar.iter("sky_condition"):
        cloud_base = skyIter.get("cloud_base_ft_agl") or 0
        try:
            cloud_base_int = int(cloud_base)
        except Exception:
            cloud_base_int = 0
        skyCond = { "cover" : (skyIter.get("sky_cover") or ""), "cloudBaseFt": cloud_base_int }
        skyConditions.append(skyCond)

    rawText = safe_text(metar.find('raw_text'), "")
    lightning = False if ((rawText.find('LTG', 4) == -1 and rawText.find('TS', 4) == -1) or rawText.find('TSNO', 4) != -1) else True

    print(f"{stationId}:{flightCategory}:{windDir}@{windSpeed}{('G'+str(windGustSpeed)) if windGust else ''}:{vis}SM:{obs}:{tempC}/{dewpointC}:{altimHg}:{lightning}")

    conditionDict[stationId] = {
        "flightCategory" : flightCategory,
        "windDir": windDir,
        "windSpeed" : windSpeed,
        "windGustSpeed": windGustSpeed,
        "windGust": windGust,
        "vis": vis,
        "obs" : obs,
        "tempC" : tempC,
        "dewpointC" : dewpointC,
        "altimHg" : altimHg,
        "lightning": lightning,
        "skyConditions" : skyConditions,
        "obsTime": obsTime
    }

    if displayairports is None or stationId in displayairports:
        stationList.append(stationId)

# Ensure every airport from your airports file has an entry
for ap in airports:
    if ap == "NULL":
        continue
    if ap not in conditionDict:
        conditionDict[ap] = {
            "flightCategory": "NONE",
            "windDir": "",
            "windSpeed": 0,
            "windGustSpeed": 0,
            "windGust": False,
            "vis": 0,
            "obs": "",
            "tempC": 0,
            "dewpointC": 0,
            "altimHg": 0.0,
            "lightning": False,
            "skyConditions": [],
            "obsTime": datetime.datetime.now()
        }
        if displayairports is None or ap in displayairports:
            stationList.append(ap)

# Start external display if available
disp = None
if displaymetar is not None and ACTIVATE_EXTERNAL_METAR_DISPLAY:
    print("setting up external display")
    disp = displaymetar.startDisplay()
    displaymetar.clearScreen(disp)

# Setting LED colors based on weather conditions
looplimit = int(round(BLINK_TOTALTIME_SECONDS / BLINK_SPEED)) if (ACTIVATE_WINDCONDITION_ANIMATION or ACTIVATE_LIGHTNING_ANIMATION or ACTIVATE_EXTERNAL_METAR_DISPLAY) else 1

windCycle = False
displayTime = 0.0
displayAirportCounter = 0
numAirports = len(stationList)

while looplimit > 0:
    i = 0
    for airportcode in airports:
        if airportcode == "NULL":
            i += 1
            continue

        color = COLOR_CLEAR
        conditions = conditionDict.get(airportcode, None)
        windy = False
        highWinds = False
        lightningConditions = False

        if conditions is not None:
            # If this airport had no METAR -> show gray
            if conditions.get("flightCategory") == "NONE":
                color = COLOR_NONE
            else:
                windy = True if (ACTIVATE_WINDCONDITION_ANIMATION and windCycle == True and (conditions["windSpeed"] >= WIND_BLINK_THRESHOLD or conditions["windGust"] == True)) else False
                highWinds = True if (windy and HIGH_WINDS_THRESHOLD != -1 and (conditions["windSpeed"] >= HIGH_WINDS_THRESHOLD or conditions["windGustSpeed"] >= HIGH_WINDS_THRESHOLD)) else False
                lightningConditions = True if (ACTIVATE_LIGHTNING_ANIMATION and windCycle == False and conditions["lightning"] == True) else False

                fc = conditions.get("flightCategory", "")
                # Explicit logic (easier to reason about than nested ternaries)
                if fc == "VFR":
                    if lightningConditions:
                        color = COLOR_LIGHTNING
                    elif highWinds:
                        color = COLOR_HIGH_WINDS
                    elif windy:
                        color = COLOR_VFR_FADE if FADE_INSTEAD_OF_BLINK else COLOR_CLEAR
                    else:
                        color = COLOR_VFR
                elif fc == "MVFR":
                    if lightningConditions:
                        color = COLOR_LIGHTNING
                    elif highWinds:
                        color = COLOR_HIGH_WINDS
                    elif windy:
                        color = COLOR_MVFR_FADE if FADE_INSTEAD_OF_BLINK else COLOR_CLEAR
                    else:
                        color = COLOR_MVFR
                elif fc == "IFR":
                    if lightningConditions:
                        color = COLOR_LIGHTNING
                    elif highWinds:
                        color = COLOR_HIGH_WINDS
                    elif windy:
                        color = COLOR_IFR_FADE if FADE_INSTEAD_OF_BLINK else COLOR_CLEAR
                    else:
                        color = COLOR_IFR
                elif fc == "LIFR":
                    if lightningConditions:
                        color = COLOR_LIGHTNING
                    elif highWinds:
                        color = COLOR_HIGH_WINDS
                    elif windy:
                        color = COLOR_LIFR_FADE if FADE_INSTEAD_OF_BLINK else COLOR_CLEAR
                    else:
                        color = COLOR_LIFR
                else:
                    color = COLOR_CLEAR

        print("Setting LED " + str(i) + " for " + airportcode + " to " + ("lightning " if lightningConditions else "") + ("very " if highWinds else "") + ("windy " if windy else "") + (conditions["flightCategory"] if conditions is not None else "None") + " " + str(color))
        pixels[i] = color
        i += 1

    # Legend
    if SHOW_LEGEND:
        pixels[i + OFFSET_LEGEND_BY] = COLOR_VFR
        pixels[i + OFFSET_LEGEND_BY + 1] = COLOR_MVFR
        pixels[i + OFFSET_LEGEND_BY + 2] = COLOR_IFR
        pixels[i + OFFSET_LEGEND_BY + 3] = COLOR_LIFR
        if ACTIVATE_LIGHTNING_ANIMATION == True:
            pixels[i + OFFSET_LEGEND_BY + 4] = COLOR_LIGHTNING if windCycle else COLOR_VFR
        if ACTIVATE_WINDCONDITION_ANIMATION == True:
            pixels[i+ OFFSET_LEGEND_BY + 5] = COLOR_VFR if not windCycle else (COLOR_VFR_FADE if FADE_INSTEAD_OF_BLINK else COLOR_CLEAR)
            if HIGH_WINDS_THRESHOLD != -1:
                pixels[i + OFFSET_LEGEND_BY + 6] = COLOR_VFR if not windCycle else COLOR_HIGH_WINDS

    # Update LEDs
    pixels.show()

    # External display rotation
    if disp is not None:
        if displayTime <= DISPLAY_ROTATION_SPEED:
            displaymetar.outputMetar(disp, stationList[displayAirportCounter], conditionDict.get(stationList[displayAirportCounter], None))
            displayTime += BLINK_SPEED
        else:
            displayTime = 0.0
            displayAirportCounter = displayAirportCounter + 1 if displayAirportCounter < numAirports-1 else 0
            print("showing METAR Display for " + stationList[displayAirportCounter])

    time.sleep(BLINK_SPEED)
    windCycle = False if windCycle else True
    looplimit -= 1

print()
print("Done")
