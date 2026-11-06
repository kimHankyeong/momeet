import { useNavigate } from 'react-router-dom';

const MENUS = [
  { key: 'room', label: '내 약속방', path: null },
  { key: 'joined', label: '참여한 약속', path: '/meetings/joined' },
  { key: 'settings', label: '설정', path: '/meetings/settings' },
];

// active: 'room' | 'joined' | 'settings'
// roomPath: 내 약속방 메뉴를 눌렀을 때 이동할 주소 (없으면 이동 안 함)
export default function MeetingLayout({ active, roomPath, children }) {
  const navigate = useNavigate();

  const go = (m) => {
    if (m.key === 'room') {
      if (roomPath) navigate(roomPath);
    } else {
      navigate(m.path);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="flex-1 flex max-w-6xl w-full mx-auto px-6 py-8 gap-8">
        <aside className="w-44 shrink-0 space-y-1.5 pt-2">
          {MENUS.map((m) => (
            <div
              key={m.key}
              onClick={() => go(m)}
              className={
                m.key === active
                  ? 'px-4 py-2.5 bg-[#6C5CE7] text-white font-bold rounded-xl text-sm w-full cursor-pointer'
                  : 'px-4 py-2.5 text-gray-400 font-medium rounded-xl text-sm cursor-pointer hover:bg-gray-100'
              }
            >
              {m.label}
            </div>
          ))}
        </aside>
        <main className="flex-1 min-w-0 space-y-6">{children}</main>
      </div>
    </div>
  );
}