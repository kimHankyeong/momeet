import './Header.css';

function Header({ onCreateClick }) {
  return (
    <header className="header">
      <div className="header__inner">
        <a href="/" className="header__logo">
          momeet<span className="header__logo-dot">.</span>
        </a>

        <nav className="header__nav">
          <span className="header__link">서비스 소개</span>
          <span className="header__link">이용 가이드</span>
          <button className="header__cta" onClick={onCreateClick}>
            새 약속 만들기
          </button>
        </nav>
      </div>
    </header>
  );
}

export default Header;