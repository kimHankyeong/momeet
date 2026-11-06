import { useEffect, useRef, useState } from 'react';
import { nearbyStations, searchPlaces } from '../api/meetApi';
import { linesLabel, stationLabel } from '../utils/station';
import StationInput from './StationInput';
import StationMap from './StationMap/StationMap';

const INPUT =
  'w-full py-3.5 px-4 bg-[#F5F5F7] border-none rounded-full text-sm text-center placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]';

// 출발지 고르기: 장소·주소 검색 → 지도 확인 → 근처 역 추천 → 출발역
// value: { place, lat, lng, station }  (lat/lng는 검색 목록에서 골랐을 때만 있음)
// 장소 검색을 쓸 수 없으면(티맵 키 없음 등) 글자만 입력해도 된다. 이때는 집→역 도보가 계산되지 않음
export default function OriginPicker({ value, onChange, onEnter, autoFocus = false }) {
  const [places, setPlaces] = useState([]);
  const [open, setOpen] = useState(false);
  const [placeMsg, setPlaceMsg] = useState('');
  const [nearbyFor, setNearbyFor] = useState({ key: '', stations: [] }); // 좌표별 근처 역
  const picked = useRef(value.lat != null ? value.place : '');

  const set = (patch) => onChange({ ...value, ...patch });

  // 장소 검색: 입력이 멈춘 뒤 0.4초 (서버 안내: 글자마다 부르지 않기)
  useEffect(() => {
    const q = value.place.trim();
    if (q.length < 2 || value.place === picked.current) {
      setPlaces([]);
      return undefined;
    }
    let alive = true;
    const t = setTimeout(() => {
      searchPlaces(q)
        .then((res) => {
          if (!alive) return;
          setPlaces(res.places || []);
          setPlaceMsg(res.places?.length ? '' : '검색 결과가 없어요. "안양 귀인로 237"처럼 입력해 보세요.');
          setOpen(true);
        })
        .catch((e) => {
          if (!alive) return;
          setPlaces([]);
          const code = e.response?.data?.error?.code;
          setPlaceMsg(
            code === 'RATE_LIMITED'
              ? '검색이 너무 많아요. 잠시 뒤 다시 시도해 주세요.'
              : '지금은 주소 검색을 쓸 수 없어요. 출발역만 정확히 골라 주세요.',
          );
        });
    }, 400);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [value.place]);

  // 위치가 정해지면 근처 역 추천
  const coordKey = value.lat == null ? '' : `${value.lat},${value.lng}`;
  useEffect(() => {
    if (!coordKey) return undefined;
    let alive = true;
    nearbyStations(value.lat, value.lng)
      .then((res) => alive && setNearbyFor({ key: coordKey, stations: res.stations || [] }))
      .catch(() => alive && setNearbyFor({ key: coordKey, stations: [] }));
    return () => {
      alive = false;
    };
  }, [coordKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const nearbyLoaded = nearbyFor.key === coordKey;
  const nearby = nearbyLoaded ? nearbyFor.stations : [];

  const pickPlace = (p) => {
    picked.current = p.name;
    setPlaces([]);
    setOpen(false);
    setPlaceMsg('');
    set({ place: p.name, lat: p.lat, lng: p.lng });
  };

  return (
    <div className="space-y-2">
      <div className="relative">
        <input
          type="text"
          placeholder="출발지 (주소·장소 검색)"
          value={value.place}
          onChange={(e) => {
            picked.current = '';
            setPlaceMsg('');
            set({ place: e.target.value, lat: undefined, lng: undefined }); // 다시 입력하면 위치 해제
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && open && places.length) {
              e.preventDefault();
              pickPlace(places[0]);
            } else if (e.key === 'Escape') setOpen(false);
          }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onFocus={() => places.length && setOpen(true)}
          className={INPUT}
          autoFocus={autoFocus}
        />
        {open && places.length > 0 && (
          <ul className="absolute z-10 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-2xl shadow-lg max-h-56 overflow-y-auto text-left">
            {places.map((p) => (
              <li key={`${p.name}-${p.lat}-${p.lng}`}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pickPlace(p)}
                  className="w-full px-4 py-2.5 hover:bg-gray-50 text-left"
                >
                  <p className="text-sm font-medium text-gray-900">{p.name}</p>
                  <p className="text-xs text-gray-500">{p.address}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {placeMsg && <p className="text-[11px] text-gray-400">{placeMsg}</p>}

      {value.lat != null && (
        <>
          <StationMap lat={value.lat} lng={value.lng} name={value.place} className="h-[160px]" />
          {nearby.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 justify-center">
              {nearby.map((st) => {
                const on = st.name === value.station;
                return (
                  <button
                    key={st.name}
                    type="button"
                    onClick={() => set({ station: st.name })}
                    className={`px-3 py-1.5 rounded-full text-xs border ${
                      on ? 'bg-[#6C5CE7] text-white border-[#6C5CE7]' : 'border-gray-300 text-gray-700 hover:border-[#6C5CE7]'
                    }`}
                  >
                    {stationLabel(st.name)} · {linesLabel(st.lines)} · 도보 {st.walk_min}분
                  </button>
                );
              })}
            </div>
          ) : (
            nearbyLoaded && (
              <p className="text-[11px] text-gray-400">걸어갈 만한 거리(약 3km) 안에 지하철역이 없어요.</p>
            )
          )}
        </>
      )}

      <StationInput
        value={value.station}
        onChange={(station) => set({ station })}
        onEnter={onEnter}
        className={INPUT}
      />
    </div>
  );
}
