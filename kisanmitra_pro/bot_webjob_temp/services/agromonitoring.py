"""
agromonitoring.py — AgroMonitoring Satellite + Soil API
=======================================================
Free tier: 10 polygons/month, NDVI + soil moisture/temp.
Fallback: NASA POWER API (already used in satellite.py).
Returns normalized dicts for the fusion layer.
"""

import time
import requests
from config import AGROMONITORING_API_KEY

# ─── In-memory polygon cache (polygon_key → polygon_id) ─────────────────────
_polygon_cache: dict[str, str] = {}

AGRO_BASE = "https://api.agromonitoring.com/agri/1.0"


def get_satellite_summary(lat: float, lon: float, location: str = "") -> dict:
    """
    Top-level entry. Returns satellite NDVI + soil data.

    Returns
    -------
    dict with keys:
        ndvi           : float or None
        ndvi_status    : str — 'Excellent'/'Good'/'Average'/'Poor'
        ndvi_trend     : str — '↗ Improving' / '↘ Declining' / '→ Stable'
        soil_moisture  : float or None (m³/m³)
        soil_temp      : float or None (°C)
        data_source    : str — 'AgroMonitoring Satellite' or 'NASA POWER'
        raw_summary    : str — human-readable summary
    """
    if AGROMONITORING_API_KEY:
        try:
            result = _agro_pipeline(lat, lon, location)
            if result:
                return result
        except Exception as e:
            print(f"[agromonitoring] API error, falling back to NASA: {e}")

    # Fallback: NASA POWER
    return _nasa_power_fallback(lat, lon, location)


# ─── AgroMonitoring Pipeline ────────────────────────────────────────────────

def _agro_pipeline(lat: float, lon: float, location: str) -> dict | None:
    """Full pipeline: create polygon → get NDVI → get soil."""
    poly_id = _get_or_create_polygon(lat, lon, location)
    if not poly_id:
        return None

    ndvi_data = _get_ndvi(poly_id)
    soil_data = _get_soil(poly_id)

    # Determine NDVI status
    ndvi_val = ndvi_data.get("ndvi")
    if ndvi_val is not None:
        if ndvi_val >= 0.7:
            ndvi_status = "Excellent 🟢"
        elif ndvi_val >= 0.5:
            ndvi_status = "Good 🟡"
        elif ndvi_val >= 0.3:
            ndvi_status = "Average 🟠"
        else:
            ndvi_status = "Poor 🔴"
    else:
        ndvi_status = "Data unavailable"

    ndvi_trend = ndvi_data.get("trend", "→ Stable")

    soil_moisture = soil_data.get("moisture")
    soil_temp = soil_data.get("temperature")

    # Build human-readable summary
    summary_parts = [f"🛰️ Satellite Report — {location}"]
    if ndvi_val is not None:
        summary_parts.append(f"• NDVI: {ndvi_val:.2f} ({ndvi_status})")
        summary_parts.append(f"• Trend: {ndvi_trend}")
    if soil_moisture is not None:
        summary_parts.append(f"• Soil moisture: {soil_moisture:.3f} m³/m³")
    if soil_temp is not None:
        summary_parts.append(f"• Soil temp: {soil_temp:.1f}°C")
    summary_parts.append("📡 Source: AgroMonitoring Satellite")

    return {
        "ndvi": ndvi_val,
        "ndvi_status": ndvi_status,
        "ndvi_trend": ndvi_trend,
        "soil_moisture": soil_moisture,
        "soil_temp": soil_temp,
        "data_source": "AgroMonitoring Satellite",
        "raw_summary": "\n".join(summary_parts),
    }


def _get_or_create_polygon(lat: float, lon: float, name: str) -> str | None:
    """Create a ~5ha square polygon around lat/lon. Returns polygon ID."""
    cache_key = f"{lat:.4f}_{lon:.4f}"
    if cache_key in _polygon_cache:
        return _polygon_cache[cache_key]

    # Build a ~224m x 224m square (~5 hectares)
    delta = 0.001  # ~111m at equator
    geo_json = {
        "type": "Feature",
        "properties": {"name": name or f"Field_{cache_key}"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon - delta, lat - delta],
                [lon + delta, lat - delta],
                [lon + delta, lat + delta],
                [lon - delta, lat + delta],
                [lon - delta, lat - delta],
            ]]
        }
    }

    resp = requests.post(
        f"{AGRO_BASE}/polygons",
        params={"appid": AGROMONITORING_API_KEY},
        json=geo_json,
        timeout=10,
    )

    if resp.status_code in (200, 201):
        poly_id = resp.json().get("id")
        if poly_id:
            _polygon_cache[cache_key] = poly_id
            print(f"[agromonitoring] Created polygon {poly_id} for {name}")
            return poly_id

    # If polygon already exists (409), try to list and find it
    if resp.status_code == 409:
        return _find_existing_polygon(lat, lon)

    print(f"[agromonitoring] Polygon create failed: {resp.status_code} — {resp.text[:200]}")
    return None


def _find_existing_polygon(lat: float, lon: float) -> str | None:
    """List all polygons and find match by proximity."""
    try:
        resp = requests.get(
            f"{AGRO_BASE}/polygons",
            params={"appid": AGROMONITORING_API_KEY},
            timeout=10,
        )
        if resp.status_code == 200:
            polygons = resp.json()
            for p in polygons:
                center = p.get("center", [])
                if center and len(center) >= 2:
                    if abs(center[0] - lon) < 0.01 and abs(center[1] - lat) < 0.01:
                        cache_key = f"{lat:.4f}_{lon:.4f}"
                        _polygon_cache[cache_key] = p["id"]
                        return p["id"]
    except Exception as e:
        print(f"[agromonitoring] List polygons error: {e}")
    return None


def _get_ndvi(polygon_id: str) -> dict:
    """Fetch satellite NDVI for polygon. Returns {ndvi, trend}."""
    try:
        # Get satellite imagery list
        end_ts = int(time.time())
        start_ts = end_ts - (30 * 86400)  # Last 30 days

        resp = requests.get(
            f"{AGRO_BASE}/image/search",
            params={
                "polyid": polygon_id,
                "start": start_ts,
                "end": end_ts,
                "appid": AGROMONITORING_API_KEY,
            },
            timeout=10,
        )

        if resp.status_code != 200 or not resp.json():
            return {"ndvi": None, "trend": "→ Stable"}

        images = resp.json()
        # Filter for low cloud cover
        valid = [img for img in images if img.get("cl", 100) < 50]
        if not valid:
            valid = images  # Use whatever we have

        # Sort by date (newest first)
        valid.sort(key=lambda x: x.get("dt", 0), reverse=True)

        # Get NDVI stats from the latest image
        latest = valid[0]
        stats_url = latest.get("stats", {}).get("ndvi")
        if not stats_url:
            # Try direct stats endpoint
            stats_url = latest.get("image", {}).get("stats")

        ndvi_val = None
        if stats_url:
            try:
                stats_resp = requests.get(stats_url, timeout=10)
                if stats_resp.status_code == 200:
                    stats = stats_resp.json()
                    ndvi_val = stats.get("mean") or stats.get("median")
            except Exception:
                pass

        # Calculate trend if we have multiple images
        trend = "→ Stable"
        if len(valid) >= 2 and ndvi_val is not None:
            older = valid[-1]
            older_stats_url = older.get("stats", {}).get("ndvi")
            if older_stats_url:
                try:
                    older_resp = requests.get(older_stats_url, timeout=10)
                    if older_resp.status_code == 200:
                        older_stats = older_resp.json()
                        older_ndvi = older_stats.get("mean") or older_stats.get("median")
                        if older_ndvi is not None:
                            diff = ndvi_val - older_ndvi
                            if diff > 0.05:
                                trend = "↗ Improving"
                            elif diff < -0.05:
                                trend = "↘ Declining"
                except Exception:
                    pass

        return {"ndvi": ndvi_val, "trend": trend}

    except Exception as e:
        print(f"[agromonitoring] NDVI fetch error: {e}")
        return {"ndvi": None, "trend": "→ Stable"}


def _get_soil(polygon_id: str) -> dict:
    """Fetch current soil temperature and moisture."""
    try:
        resp = requests.get(
            f"{AGRO_BASE}/soil",
            params={
                "polyid": polygon_id,
                "appid": AGROMONITORING_API_KEY,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            return {"moisture": None, "temperature": None}

        data = resp.json()
        moisture = data.get("moisture")
        t10 = data.get("t10")  # Temperature at 10cm depth
        t0 = data.get("t0")   # Surface temperature

        temp = None
        if t10 is not None:
            temp = t10 - 273.15  # Convert Kelvin to Celsius
        elif t0 is not None:
            temp = t0 - 273.15

        return {
            "moisture": moisture,
            "temperature": round(temp, 1) if temp is not None else None,
        }

    except Exception as e:
        print(f"[agromonitoring] Soil fetch error: {e}")
        return {"moisture": None, "temperature": None}


# ─── NASA POWER Fallback ────────────────────────────────────────────────────

def _nasa_power_fallback(lat: float, lon: float, location: str) -> dict:
    """
    Fallback using NASA POWER API (free, no key needed).
    Derives a pseudo-NDVI from solar radiation + temperature + rainfall.
    """
    try:
        url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=ALLSKY_SFC_SW_DWN,T2M,PRECTOTCORR,RH2M"
            f"&community=AG&longitude={lon}&latitude={lat}"
            f"&start=20250301&end=20250308&format=JSON"
        )
        res = requests.get(url, timeout=10)
        data = res.json()

        props = data.get("properties", {}).get("parameter", {})
        if not props:
            return _empty_satellite_result(location)

        solar = [v for v in props.get("ALLSKY_SFC_SW_DWN", {}).values() if v > 0]
        temp = [v for v in props.get("T2M", {}).values() if v > -900]
        rain = [v for v in props.get("PRECTOTCORR", {}).values() if v >= 0]
        humidity = [v for v in props.get("RH2M", {}).values() if v > 0]

        avg_temp = sum(temp) / len(temp) if temp else 0
        avg_rain = sum(rain) / len(rain) if rain else 0
        avg_humidity = sum(humidity) / len(humidity) if humidity else 0

        # Derive pseudo NDVI from conditions (rough agronomic estimate)
        pseudo_ndvi = 0.3  # Baseline
        if 20 <= avg_temp <= 35:
            pseudo_ndvi += 0.15
        if avg_rain > 2:
            pseudo_ndvi += 0.15
        if 50 <= avg_humidity <= 80:
            pseudo_ndvi += 0.1

        pseudo_ndvi = min(pseudo_ndvi, 0.9)

        if pseudo_ndvi >= 0.7:
            status = "Excellent 🟢"
        elif pseudo_ndvi >= 0.5:
            status = "Good 🟡"
        elif pseudo_ndvi >= 0.3:
            status = "Average 🟠"
        else:
            status = "Poor 🔴"

        # Estimate soil moisture from rainfall + humidity
        est_moisture = min(0.4, avg_rain * 0.02 + avg_humidity * 0.002)

        summary = (
            f"🛰️ Satellite Report — {location}\n"
            f"• Estimated NDVI: {pseudo_ndvi:.2f} ({status})\n"
            f"• Avg Temp: {avg_temp:.1f}°C | Rain: {avg_rain:.1f}mm/day\n"
            f"• Est. Soil Moisture: {est_moisture:.3f} m³/m³\n"
            f"📡 Source: NASA POWER (Estimated)"
        )

        return {
            "ndvi": round(pseudo_ndvi, 2),
            "ndvi_status": status,
            "ndvi_trend": "→ Stable (estimated)",
            "soil_moisture": round(est_moisture, 3),
            "soil_temp": round(avg_temp, 1),
            "data_source": "NASA POWER (Estimated)",
            "raw_summary": summary,
        }

    except Exception as e:
        print(f"[agromonitoring] NASA POWER fallback error: {e}")
        return _empty_satellite_result(location)


def _empty_satellite_result(location: str) -> dict:
    """Return empty result when all satellite sources fail."""
    return {
        "ndvi": None,
        "ndvi_status": "Data unavailable",
        "ndvi_trend": "→ Unknown",
        "soil_moisture": None,
        "soil_temp": None,
        "data_source": "Unavailable",
        "raw_summary": f"🛰️ Satellite data for {location} abhi available nahi hai.",
    }
