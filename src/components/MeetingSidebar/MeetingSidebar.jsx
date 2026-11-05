import { NavLink } from 'react-router-dom';
import './MeetingSidebar.css';

// TODO: "내 약속방"이 연결될 경로가 따로 있으면 여기만 바꾸세요.
const MENUS = [
  { label: '내 약속방', to: '/' },
  { label: '참여한 약속', to: '/meetings/joined' },
  { label: '설정', to: '/meetings/settings' },
];

export default function MeetingSidebar() {
  return (
    <nav className="msb">
      {MENUS.map((menu) => (
        <NavLink
          key={menu.to}
          to={menu.to}
          end
          className={({ isActive }) => `msb__item${isActive ? ' msb__item--active' : ''}`}
        >
          {menu.label}
        </NavLink>
      ))}
    </nav>
  );
}
