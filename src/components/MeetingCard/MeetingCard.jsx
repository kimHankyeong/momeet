import { useNavigate } from 'react-router-dom';
import './MeetingCard.css';

const STAGES = ['모집', '입력', '추천', '제안', '확정'];

// meeting: { id, name, dateLabel, place, participants, maxParticipants, stage, ended, daysUntilDelete }
export default function MeetingCard({ meeting }) {
  const navigate = useNavigate();
  const { id, name, dateLabel, place, participants, maxParticipants, stage, ended, daysUntilDelete } = meeting;

  // 종료된 약속 카드 (회색)
  if (ended) {
    return (
      <div className="mcard mcard--ended">
        {daysUntilDelete != null && (
          <span className="mcard__badge">{daysUntilDelete}일 뒤 삭제 예정</span>
        )}
        <h4 className="mcard__name">{name}</h4>
        <p className="mcard__info">{dateLabel}</p>
        <p className="mcard__info">📍 {place}</p>
        <p className="mcard__foot-text">{participants}명 참여 · 약속 종료</p>
      </div>
    );
  }

  // 진행 중 약속 카드 (보라색 테두리)
  return (
    <div className="mcard mcard--active">
      <div className="mcard__stages">
        {STAGES.map((s, i) => (
          <span key={s}>
            {i > 0 && <span className="mcard__dot"> · </span>}
            <span className={s === stage ? 'mcard__stage--current' : ''}>{s}</span>
          </span>
        ))}
      </div>

      <h4 className="mcard__name">{name}</h4>
      <p className="mcard__info">{dateLabel}</p>
      <p className="mcard__info">📍 {place}</p>

      <div className="mcard__foot">
        <span className="mcard__people">
          {participants}/{maxParticipants} 참여 중
        </span>
        <button type="button" className="mcard__btn" onClick={() => navigate(`/meet/${id}`)}>
          상세보기
        </button>
      </div>
    </div>
  );
}