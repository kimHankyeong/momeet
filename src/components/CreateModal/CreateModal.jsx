import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from '../Modal/Modal';
import Input from '../Input/Input';
import Button from '../Button/Button';
import DateRangeInput from '../DateRangeInput/DateRangeInput';
import './CreateModal.css';

function CreateModal({ isOpen, onClose }) {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [dateRange, setDateRange] = useState();
  const [pin, setPin] = useState('');
  const [password, setPassword] = useState('');

  const isValid =
    name && dateRange?.from && dateRange?.to && pin.length === 6 && password;

  const handleSubmit = () => {
    // TODO: 백엔드 API로 방 생성 후 받은 id 사용
    onClose();
    navigate(`/meet/${pin}/setup`);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2 className="create__title">새로운 약속을 만들어요</h2>
      <p className="create__desc">약속 이름과 가능한 날짜 범위를 설정해 주세요.</p>

      <Input
        label="약속 이름이 무엇인가요?"
        hint="최대 12자 이내로 만들어 주세요"
        value={name}
        maxLength={12}
        onChange={(e) => setName(e.target.value)}
      />

      <div className="field">
        <label className="field__label">언제쯤 만날 예정인가요?</label>
        <DateRangeInput value={dateRange} onChange={setDateRange} />
      </div>

      <Input
        label="방 PIN을 설정해주세요."
        placeholder="숫자 6자리"
        value={pin}
        maxLength={6}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
      />

      <Input
        label="방장 비밀번호를 설정해주세요."
        type="password"
        placeholder="최대 8자리"
        value={password}
        maxLength={8}
        onChange={(e) => setPassword(e.target.value)}
      />

      <div className="create__submit">
        <Button size="lg" disabled={!isValid} onClick={handleSubmit}>
          약속 만들기
        </Button>
      </div>
    </Modal>
  );
}

export default CreateModal;