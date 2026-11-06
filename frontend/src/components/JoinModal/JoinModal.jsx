import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from '../Modal/Modal';
import Input from '../Input/Input';
import Button from '../Button/Button';
import { hostLogin, joinMeeting, previewJoin, saveToken, stagePath } from '../../api/meetApi';
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
  // 방장 재접속: 닉네임은 누구나 같게 쓸 수 있어 방장 확인은 방을 만들 때 정한 비밀번호로 한다
  const [asHost, setAsHost] = useState(false);
  const [password, setPassword] = useState('');

  const isValid = code.trim() && (asHost ? password : nickname.trim());

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      if (asHost) {
        const { meeting_id: id, stage } = await previewJoin(extractCode(code));
        const res = await hostLogin(id, password);
        saveToken(id, res.access_token);
        onClose();
        navigate(stagePath(id, stage));
        return;
      }

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
      <h2 className="join__title">{asHost ? '방장으로 다시 들어가요' : '약속에 참여해요'}</h2>

      {pending ? (
        <p className="join__card-date" style={{ textAlign: 'center', margin: '32px 0' }}>
          방장의 승인을 기다리고 있어요.
        </p>
      ) : (
        <>
          <Input label="입장 코드 또는 링크를 입력해주세요." placeholder="입장 코드"
            value={code} onChange={(e) => setCode(e.target.value)} />

          {asHost ? (
            <Input label="방장 비밀번호를 입력해주세요." type="password" placeholder="방을 만들 때 정한 비밀번호"
              value={password} maxLength={72} onChange={(e) => setPassword(e.target.value)} />
          ) : (
            <Input label="닉네임을 정해주세요." placeholder="닉네임" hint="최대 8자 이내로 만들어 주세요"
              value={nickname} maxLength={8} onChange={(e) => setNickname(e.target.value)} />
          )}

          {error && <p className="field__hint" style={{ color: '#e5484d' }}>{error}</p>}

          <button type="button" className="join__switch"
            onClick={() => { setAsHost((v) => !v); setError(''); }}>
            {asHost ? '참여자로 들어가기' : '방장이신가요? 비밀번호로 다시 들어가기'}
          </button>

          <div className="join__submit">
            <Button size="lg" disabled={!isValid || loading} onClick={handleSubmit}>
              {asHost ? '방장으로 들어가기' : '참여하기'}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}

export default JoinModal;