import { useState } from 'react';
import Modal from '../Modal/Modal';
import Input from '../Input/Input';
import Button from '../Button/Button';
import './JoinModal.css';

function JoinModal({ isOpen, onClose }) {
  const [pin, setPin] = useState('');
  const [nickname, setNickname] = useState('');

  const isValid = pin && nickname;

  const handleSubmit = () => {
    console.log({ pin, nickname });
    // TODO: 백엔드 API 연결
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2 className="join__title">약속에 참여해요</h2>

      {/* 약속 정보 카드: 나중에 PIN으로 조회한 데이터로 교체 */}
      <div className="join__card">
        <p className="join__card-name">친구들과 저녁 약속</p>
        <p className="join__card-date">11월 1일 (일) - 11월 8일 (일)</p>
        <p className="join__card-status">모집 중</p>
      </div>

      <Input label="방 PIN 또는 링크를 입력해주세요." placeholder="초대 링크"
        value={pin} onChange={(e) => setPin(e.target.value)} />

      <Input label="닉네임을 정해주세요." placeholder="닉네임" hint="최대 8자 이내로 만들어 주세요"
        value={nickname} maxLength={8} onChange={(e) => setNickname(e.target.value)} />

      <div className="join__submit">
        <Button size="lg" disabled={!isValid} onClick={handleSubmit}>참여하기</Button>
      </div>
    </Modal>
  );
}

export default JoinModal;