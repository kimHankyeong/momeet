import { useState } from 'react';
import Header from './components/Header/Header';
import Home from './pages/Home';
import CreateModal from './components/CreateModal/CreateModal';
import JoinModal from './components/JoinModal/JoinModal';

function App() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isJoinOpen, setIsJoinOpen] = useState(false);

  return (
    <>
      <Header onCreateClick={() => setIsCreateOpen(true)} />
      <Home
        onCreateClick={() => setIsCreateOpen(true)}
        onJoinClick={() => setIsJoinOpen(true)}
      />
      <CreateModal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
      <JoinModal isOpen={isJoinOpen} onClose={() => setIsJoinOpen(false)} />
    </>
  );
}

export default App;