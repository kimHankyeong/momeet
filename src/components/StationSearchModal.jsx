import React, { useState } from 'react';

// 자주 쓰이는 지하철역 목록 (추후 Kakao/지하철 API로 교체 가능)
const POPULAR_STATIONS = [
  '강남역', '홍대입구역', '신촌역', '잠실역', '서울역',
  '고속터미널역', '사당역', '건대입구역', '여의도역', '성수역',
  '합정역', '판교역', '수원역', '인천공항1터미널역'
];

export default function StationSearchModal({ isOpen, onClose, onSelect }) {
  const [searchTerm, setSearchTerm] = useState('');

  if (!isOpen) return null;

  // 입력한 검색어로 지하철역 필터링
  const filteredStations = POPULAR_STATIONS.filter((station) =>
    station.includes(searchTerm.trim())
  );

  const handleSelect = (station) => {
    onSelect(station);
    onClose();
    setSearchTerm(''); // 검색어 초기화
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white w-full max-w-md rounded-2xl p-6 shadow-2xl space-y-4">
        
        {/* 모달 헤더 */}
        <div className="flex justify-between items-center border-b border-gray-100 pb-3">
          <h3 className="text-base font-bold text-gray-900">지하철역 / 주요 장소 검색</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 text-lg font-bold"
          >
            ✕
          </button>
        </div>

        {/* 검색어 입력창 */}
        <div>
          <input
            type="text"
            placeholder="역 이름을 입력하세요 (예: 강남, 홍대)"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:border-indigo-600 focus:bg-white text-sm transition-all"
            autoFocus
          />
        </div>

        {/* 지하철역 검색 결과 목록 */}
        <div className="max-h-60 overflow-y-auto space-y-1">
          {filteredStations.length > 0 ? (
            filteredStations.map((station) => (
              <button
                key={station}
                type="button"
                onClick={() => handleSelect(station)}
                className="w-full text-left px-4 py-3 hover:bg-indigo-50 hover:text-indigo-600 rounded-xl text-sm font-medium transition-colors border border-transparent hover:border-indigo-100 flex items-center gap-2"
              >
                <span>📍</span>
                <span>{station}</span>
              </button>
            ))
          ) : (
            <div className="text-center py-8 text-gray-400 text-sm">
              검색 결과가 없습니다.
            </div>
          )}
        </div>

        {/* 닫기 버튼 */}
        <div className="pt-2">
          <button
            type="button"
            onClick={onClose}
            className="w-full py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-600 text-sm font-medium rounded-xl transition-colors"
          >
            취소
          </button>
        </div>

      </div>
    </div>
  );
}