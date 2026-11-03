import { useState } from 'react';
import Header from './components/Header/Header';
import CreateModal from './components/CreateModal/CreateModal';
import Home from './pages/Home';

function App() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  return (
    <>
      <Header onCreateClick={() => setIsCreateOpen(true)} />
      <Home />
      <CreateModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
      />
    </>
  );
}

export default App;