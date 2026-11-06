import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// 추천 역 지도 (OpenStreetMap, API 키 불필요. 지도 아래 출처 표시는 이용 조건이라 지우지 않는다)
export default function StationMap({ lat, lng, name }) {
  const el = useRef(null);
  const map = useRef(null);
  const marker = useRef(null);

  useEffect(() => {
    map.current = L.map(el.current, { scrollWheelZoom: false });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map.current);
    return () => {
      map.current.remove();
      map.current = null;
    };
  }, []);

  // 후보를 바꾸면 그 역으로 이동하고 표시를 옮긴다
  useEffect(() => {
    if (!map.current || lat == null || lng == null) return;
    map.current.setView([lat, lng], 16);
    marker.current?.remove();
    // 기본 핀 이미지는 번들 경로 문제가 있어 원형 표시를 쓴다
    marker.current = L.circleMarker([lat, lng], {
      radius: 10,
      color: '#6C5CE7',
      weight: 3,
      fillColor: '#6C5CE7',
      fillOpacity: 0.85,
    })
      .bindTooltip(name, { permanent: true, direction: 'top', offset: [0, -10] })
      .addTo(map.current);
  }, [lat, lng, name]);

  // isolate: 지도 레이어(z-index 400~1000)가 헤더·모달 위로 올라오지 않게 한다
  return <div ref={el} className="isolate w-full h-[280px] rounded-2xl overflow-hidden" />;
}
