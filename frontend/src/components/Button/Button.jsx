import './Button.css';

function Button({ variant = 'primary', size = 'md', children, ...rest }) {
  return (
    <button className={`btn btn--${variant} btn--${size}`} {...rest}>
      {children}
    </button>
  );
}

export default Button;