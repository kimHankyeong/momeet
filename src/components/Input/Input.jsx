import './Input.css';

function Input({ label, hint, ...rest }) {
  return (
    <div className="field">
      {label && <label className="field__label">{label}</label>}
      <input className="field__input" {...rest} />
      {hint && <p className="field__hint">{hint}</p>}
    </div>
  );
}

export default Input;