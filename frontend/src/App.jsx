import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, useParams } from 'react-router-dom';
import Header from './components/Header/Header';
import Home from './pages/Home';
import SetupPage from './pages/SetupPage';
import ProposalPage from './pages/ProposalPage';
import CreateModal from './components/CreateModal/CreateModal';
import JoinModal from './components/JoinModal/JoinModal';
import RecommendPage from './pages/RecommendPage';
import JoinedMeetingsPage from './pages/JoinedMeetingsPage'; // [추가]
import SettingsPage from './pages/SettingsPage'; // [추가]



// 초대 링크 /join/{입장코드}: 홈 화면 위에 참여 창을 코드가 채워진 상태로 연다
function JoinLink({ onOpen, ...homeProps }) {
  const { code } = useParams();
  useEffect(() => {
    onOpen(code);
  }, [code, onOpen]);
  return <Home {...homeProps} />;
}

function App() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isJoinOpen, setIsJoinOpen] = useState(false);
  const [joinCode, setJoinCode] = useState('');

  // useCallback: 참여 창을 닫은 뒤 다시 열리지 않도록 같은 함수를 유지
  const openJoin = useCallback((code) => {
    setJoinCode(code);
    setIsJoinOpen(true);
  }, []);

  return (
    <BrowserRouter>
      <Header onCreateClick={() => setIsCreateOpen(true)} />

      <Routes>
        <Route
          path="/"
          element={
            <Home
              onCreateClick={() => setIsCreateOpen(true)}
              onJoinClick={() => setIsJoinOpen(true)}
            />
          }
        />
        <Route
          path="/join/:code"
          element={
            <JoinLink
              onOpen={openJoin}
              onCreateClick={() => setIsCreateOpen(true)}
              onJoinClick={() => setIsJoinOpen(true)}
            />
          }
        />
        {/* [추가] 참여한 약속 / 설정 */}
        <Route path="/meetings/joined" element={<JoinedMeetingsPage />} />
        <Route path="/meetings/settings" element={<SettingsPage />} />
        <Route path="/meet/:id/setup" element={<SetupPage />} />
        <Route path="/meet/:id/proposal" element={<ProposalPage />} />
        <Route path="/meet/:id/recommend" element={<RecommendPage />} />
      </Routes>

      <CreateModal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
      {/* key: 초대 링크 코드가 바뀌면 참여 창을 새로 만들어 코드를 채운다 */}
      <JoinModal key={joinCode} isOpen={isJoinOpen} onClose={() => setIsJoinOpen(false)} initialCode={joinCode} />
    </BrowserRouter>
  );
}

export default App;
