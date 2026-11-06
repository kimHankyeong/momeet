import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Header from './components/Header/Header';
import Home from './pages/Home';
import SetupPage from './pages/SetupPage';
import ProposalPage from './pages/ProposalPage';
import CreateModal from './components/CreateModal/CreateModal';
import JoinModal from './components/JoinModal/JoinModal';
import RecommendPage from './pages/RecommendPage';
import JoinedMeetingsPage from './pages/JoinedMeetingsPage'; // [추가]
import SettingsPage from './pages/SettingsPage'; // [추가]
import InvitePage from './pages/InvitePage';



function App() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isJoinOpen, setIsJoinOpen] = useState(false);

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
        {/* [추가] 참여한 약속 / 설정 */}
        <Route path="/meetings/joined" element={<JoinedMeetingsPage />} />
        <Route path="/meetings/settings" element={<SettingsPage />} />
        <Route path="/meet/:id/setup" element={<SetupPage />} />
        <Route path="/meet/:id/proposal" element={<ProposalPage />} />
        <Route path="/meet/:id/recommend" element={<RecommendPage />} />
        {/* 초대 링크: 참여 또는 지금 단계 화면으로 이동 */}
        <Route path="/join/:code" element={<InvitePage />} />
      </Routes>

      <CreateModal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
      <JoinModal isOpen={isJoinOpen} onClose={() => setIsJoinOpen(false)} />
    </BrowserRouter>
  );
}

export default App;
