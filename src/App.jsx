import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Header from './components/Header/Header';
import Home from './pages/Home';
import SetupPage from './pages/SetupPage';
import ProposalPage from './pages/ProposalPage';
import CreateModal from './components/CreateModal/CreateModal';
import JoinModal from './components/JoinModal/JoinModal';
import RecommendPage from './pages/RecommendPage';



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
        <Route path="/meet/:id/setup" element={<SetupPage />} />
        <Route path="/meet/:id/proposal" element={<ProposalPage />} />
        <Route path="/meet/:id/recommend" element={<RecommendPage />} />
      </Routes>

      <CreateModal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
      <JoinModal isOpen={isJoinOpen} onClose={() => setIsJoinOpen(false)} />
    </BrowserRouter>
  );
}

export default App;