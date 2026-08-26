// GPS 路线地图 (V0.6.1) — 对标 Strava / GC 地图
// 用 Leaflet + OpenStreetMap tile (免费, 无需 API key)
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Sample } from "../lib/types";

interface Props {
  samples: Sample[];
  height?: number;
}

// FIT 存 semicircles (1e-7 度), 转 WGS-84
function semiToDeg(semi: number | null | undefined): number | null {
  if (semi == null) return null;
  return semi * (180 / 2 ** 31);
}

export function GPSMap({ samples, height = 360 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const [noGps, setNoGps] = useState(false);
  const [stats, setStats] = useState<{ distance: number; points: number } | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (mapRef.current) return; // 已初始化

    // 提取有效 GPS 点
    const points: [number, number][] = [];
    for (const s of samples) {
      const lat = semiToDeg(s.lat);
      const lon = semiToDeg(s.lon);
      if (lat != null && lon != null) {
        points.push([lat, lon]);
      }
    }

    if (points.length < 2) {
      setNoGps(true);
      return;
    }

    // 初始化地图
    const map = L.map(ref.current, {
      zoomControl: true,
      attributionControl: true,
    });
    mapRef.current = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);

    // 路线
    const polyline = L.polyline(points, {
      color: "#3b82f6",
      weight: 3,
      opacity: 0.8,
    }).addTo(map);

    // 起点 / 终点 marker
    L.circleMarker(points[0], { radius: 6, color: "#10b981", fillOpacity: 1 })
      .bindTooltip("起点", { permanent: false, direction: "top" })
      .addTo(map);
    L.circleMarker(points[points.length - 1], { radius: 6, color: "#dc2626", fillOpacity: 1 })
      .bindTooltip("终点", { permanent: false, direction: "top" })
      .addTo(map);

    // 自动 fit bounds
    map.fitBounds(polyline.getBounds(), { padding: [20, 20] });

    // 计算距离 (Haversine)
    let dist = 0;
    for (let i = 1; i < points.length; i++) {
      dist += haversine(points[i - 1], points[i]);
    }
    setStats({ distance: dist / 1000, points: points.length });
  }, [samples]);

  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  if (noGps) {
    return (
      <div className="text-text-muted text-sm p-4 text-center bg-slate-50 rounded-md">
        该 FIT 文件不含 GPS 数据 (室内训练 / 设备无 GPS)
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        ref={ref}
        style={{ height, width: "100%" }}
        className="rounded-md border border-border overflow-hidden"
      />
      {stats && (
        <div className="flex gap-2 text-xs text-text-muted">
          <span className="px-2 py-1 rounded bg-slate-50">
            GPS 点 {stats.points}
          </span>
          <span className="px-2 py-1 rounded bg-slate-50">
            距离 (Haversine) ≈ {stats.distance.toFixed(2)} km
          </span>
          <span className="px-2 py-1 rounded bg-slate-50 text-[10px]">
            地图: OpenStreetMap 免费瓦片, 无需 API key
          </span>
        </div>
      )}
    </div>
  );
}

function haversine(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const toRad = (d: number) => d * Math.PI / 180;
  const dLat = toRad(b[0] - a[0]);
  const dLon = toRad(b[1] - a[1]);
  const lat1 = toRad(a[0]);
  const lat2 = toRad(b[0]);
  const x = Math.sin(dLat / 2) ** 2 + Math.sin(dLon / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(x));
}
