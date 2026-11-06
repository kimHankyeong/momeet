import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from '../Modal/Modal';
import Input from '../Input/Input';
import Button from '../Button/Button';
import { joinMeeting, saveToken } from '../../api/meetApi';
import './JoinModal.css';

// 링크를 붙여넣어도 마지막 경로 조각을 코드로 사용
const extractCode = (text) => text.trim().split('/').filter(Boolean).pop() || '';

function JoinModal({ isOpen, onClose, initialCode = '' }) {
  const navigate = useNavigate();
  const [code, setCode] = useState(initialCode);
  const [nickname, setNickname] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  const isValid = code.trim() && nickname.trim();

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await joinMeeting(extractCode(code), nickname.trim());

      if (res.status === 'pending') {
        // 모집 마감 후: 호스트 승인 대기 (202)
        localStorage.setItem(`momeet_request_${res.meeting_id}`, JSON.stringify(res));
        setPending(true);
        return;
      }

      saveToken(res.meeting_id, res.access_token);
    
      onClose();
      navigate(`/meet/${res.meeting_id}/setup`);
    } catch (e) {
      setError(e.response?.data?.error?.message || '참여하지 못했어요. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2 className="join__title">약속에 참여해요</h2>

      {pending ? (
        <p className="join__card-date" style={{ textAlign: 'center', margin: '32px 0' }}>
          방장의 승인을 기다리고 있어요.
        </p>
      ) : (
        <>
          <Input label="입장 코드 또는 링크를 입력해주세요." placeholder="입장 코드"
            value={code} onChange={(e) => setCode(e.target.value)} />

          <Input label="닉네임을 정해주세요." placeholder="닉네임" hint="최대 8자 이내로 만들어 주세요"
            value={nickname} maxLength={8} onChange={(e) => setNickname(e.target.value)} />

          {error && <p className="field__hint" style={{ color: '#e5484d' }}>{error}</p>}

          <div className="join__submit">
            <Button size="lg" disabled={!isValid || loading} onClick={handleSubmit}>
              참여하기
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}

export default JoinModal;