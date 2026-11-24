import { useEffect, useRef, useState } from 'react';

export default function Stage3ReviewNotifications({ message }) {
  const [items, setItems] = useState([]);
  const queue = useRef([]);
  const timers = useRef(new Map());
  const counter = useRef(0);
  const dismiss = (id) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    queue.current = queue.current.filter(item => item.id !== id);
    setItems(queue.current);
  };
  useEffect(() => {
    if (!message?.text || queue.current.some(item => item.text === message.text && item.type === message.type)) return;
    const item = { ...message, id: ++counter.current };
    const removed = queue.current.length === 2 ? queue.current[0] : null;
    if (removed) { clearTimeout(timers.current.get(removed.id)); timers.current.delete(removed.id); }
    queue.current = [...queue.current.slice(-1), item];
    setItems(queue.current);
    timers.current.set(item.id, setTimeout(() => {
      timers.current.delete(item.id);
      queue.current = queue.current.filter(value => value.id !== item.id);
      setItems(queue.current);
    }, 5000));
  }, [message]);
  useEffect(() => {
    const active = timers.current;
    return () => { for (const timer of active.values()) clearTimeout(timer); active.clear(); queue.current = []; };
  }, []);
  return <div className="stage3-toast-region" aria-label="Thông báo thao tác">
    {items.map(item => <div key={item.id} data-review-toast role={item.type === 'error' ? 'alert' : 'status'}
      className={`stage3-toast${item.type === 'error' ? ' stage3-toast-error' : ''}`}>
      <p>{item.text}</p><button type="button" aria-label="Đóng thông báo" onClick={() => dismiss(item.id)}>×</button>
    </div>)}
  </div>;
}
