import Button from '../components/Button/Button';
import heroArt from '../assets/hero-art.svg'; 
import stepsIcons from '../assets/icon.svg';
import './Home.css';

function Home({ onCreateClick, onJoinClick }) {
  return (
    <main className="home">
      <section className="home__hero">
        <div className="home__hero-text">
          <p className="home__tagline">우리 모두에게 편한 중간 지점</p>
          <h1 className="home__title">
            momeet<span>.</span>
          </h1>
          <p className="home__desc">
            각자의 출발역과 가능한 시간을 모아 함께 만나기 좋은 장소를 찾아요.
          </p>

          <div className="home__buttons">
            <Button size="md" onClick={onCreateClick}>
              새 약속 만들기 <span className="home__btn-icon">+</span>
            </Button>
            <Button variant="light" size="md" onClick={onJoinClick}>
              초대 링크로 참여하기 <span className="home__btn-icon">→</span>
            </Button>
          </div>
        </div>
        <div className="home__hero-art">
          <img src={heroArt} alt="약속 장소 경로 일러스트" />
        </div>
      </section>

      <hr className="home__divider" />

      {/* 새로 변경된 3단계 이미지 세션 */}
      <section className="home__steps">
        <img className="home__steps-icons" src={stepsIcons} alt="이용 단계 아이콘" />
        <div className="home__steps-texts">
          <p>약속을 만들고<br />친구를 초대해요</p>
          <p>각자 가능한 시간과<br />이동 조건을 입력해요</p>
          <p>추천 장소를 확인하고<br />함께 확정해요</p>
        </div>
      </section>
    </main>
  );
}

export default Home;