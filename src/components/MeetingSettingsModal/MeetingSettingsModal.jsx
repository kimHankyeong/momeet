import { useState } from 'react';
import './MeetingSettingsModal.css';

// meeting: { id, name, reconnectLink }
export default function MeetingSettingsModal({ isOpen, meeting, onClose, onLeave }) {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !meeting) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(meeting.reconnectLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 접근이 막힌 환경에서는 입력창을 직접 선택해서 복사
    }
  };

  const handleLeave = () => {
    if (window.confirm('약속방을 나가시겠어요? 개인 링크로 다시 들어올 수 없어요.')) {
      onLeave?.(meeting.id);
      onClose();
    }
  };

  return (
    <div className="msm__overlay">
      <div className="msm">
        <div className="msm__body">
          <div className="msm__head">
            <div>
              <h3 className="msm__title">{meeting.name}</h3>
              {/* TODO: 디자인의 부제 문구는 이동 조건 단계 문구 같아요. 확인 후 수정하세요. */}
              <p className="msm__sub">아무 조건도 설정하지 않아도 괜찮아요</p>
            </div>
            <button type="button" className="msm__close" onClick={onClose}>
              나가기
            </button>
          </div>

          <p className="msm__label">🔗 개인 재접속 링크</p>
          <div className="msm__row">
            <input
              type="text"
              readOnly
              value={meeting.reconnectLink}
              onFocus={(e) => e.target.select()}
              className="msm__input"
            />
            <button type="button" className="msm__copy" onClick={handleCopy}>
              {copied ? '복사됨' : '링크 복사'}
            </button>
          </div>
        </div>

        <div className="msm__foot">
          <button type="button" className="msm__leave" onClick={handleLeave}>
            ↪ 약속방 나가기
          </button>
        </div>
      </div>
    </div>
  );
}