import './Modal.css';

function Modal({ isOpen, onClose, closeLabel = '취소', children }) {
  if (!isOpen) return null;

  return (
    <div className="modal__overlay" onClick={onClose}>
      <div className="modal__card" onClick={(e) => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose}>
          {closeLabel}
        </button>
        {children}
      </div>
    </div>
  );
}

export default Modal;