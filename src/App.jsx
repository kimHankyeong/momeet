import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Header from './components/Header/Header';
import CreateModal from './components/CreateModal/CreateModal';
import Home from './pages/Home';
import SetupPage from './pages/SetupPage';

function App() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  return (
    <BrowserRouter>
      {/* 모든 페이지 상단에 공통 헤더 띄우기 */}
      <Header onCreateClick={() => setIsCreateOpen(true)} />

      {/* URL 경로에 따른 페이지 전환 */}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/meet/:id/setup" element={<SetupPage />} />
      </Routes>

      {/* 모달 공통 컴포넌트 */}
      <CreateModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
      />
    </BrowserRouter>
  );
}

export default App;