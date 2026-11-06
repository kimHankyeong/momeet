import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from '../Modal/Modal';
import Input from '../Input/Input';
import Button from '../Button/Button';
import DateRangeInput from '../DateRangeInput/DateRangeInput';
import { createMeeting, saveToken } from '../../api/meetApi';
import { toDateString } from '../../api/transform';
import './CreateModal.css';

function CreateModal({ isOpen, onClose }) {
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [dateRange, setDateRange] = useState();
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const days =
    dateRange?.from && dateRange?.to
      ? Math.round((dateRange.to - dateRange.from) / 86400000) + 1
      : 0;

  const isValid =
    title && nickname && password.length >= 8 && days >= 2 && days <= 7;

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await createMeeting({
        title,
        date_start: toDateString(dateRange.from),
        date_end: toDateString(dateRange.to),
        host_nickname: nickname,
        host_password: password,
      });
      saveToken(res.access_token, res.meeting_id);
      localStorage.setItem(`momeet_meeting_${res.meeting_id}`, JSON.stringify(res.meeting));
      onClose();
      navigate(`/meet/${res.meeting_id}/setup`);
    } catch (e) {
      setError(e.response?.data?.error?.message || '약속을 만들지 못했어요. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2 className="create__title">새로운 약속을 만들어요</h2>
      <p className="create__desc">약속 이름과 가능한 날짜 범위를 설정해 주세요.</p>

      <Input label="약속 이름이 무엇인가요?" hint="최대 12자 이내로 만들어 주세요"
        value={title} maxLength={12} onChange={(e) => setTitle(e.target.value)} />

      <div className="field">
        <label className="field__label">언제쯤 만날 예정인가요?</label>
        <DateRangeInput value={dateRange} onChange={setDateRange} />
        {days > 7 && <p className="field__hint">날짜 범위는 최대 7일이에요.</p>}
      </div>

      <Input label="방장 닉네임을 정해주세요." placeholder="최대 8자" hint="최대 8자 이내로 만들어 주세요"
        value={nickname} maxLength={8} onChange={(e) => setNickname(e.target.value)} />

      <Input label="방장 비밀번호를 설정해주세요." type="password" placeholder="8자 이상"
        value={password} maxLength={72} onChange={(e) => setPassword(e.target.value)} />

      {error && <p className="field__hint" style={{ color: '#e5484d' }}>{error}</p>}

      <div className="create__submit">
        <Button size="lg" disabled={!isValid || loading} onClick={handleSubmit}>
          약속 만들기
        </Button>
      </div>
    </Modal>
  );
}

export default CreateModal;