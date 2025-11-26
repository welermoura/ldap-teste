import React from 'react';
// Reutilizaremos o CSS do MoveModal/EditModal para consistência

const NotificationModal = ({ isOpen, onClose, title, message }) => {
    if (!isOpen) return null;

    const isError = title.toLowerCase().includes('erro') || title.toLowerCase().includes('falha');

    return (
        <div className="modal-backdrop">
            <div className="modal-content" style={{ width: '500px' }}>
                <div className={`modal-header ${isError ? 'bg-danger text-white' : 'bg-success text-white'}`}>
                    <h5 className="modal-title">{title}</h5>
                    <button type="button" className="btn-close btn-close-white" onClick={onClose}></button>
                </div>
                <div className="modal-body">
                    <p>{message}</p>
                </div>
                <div className="modal-footer">
                    <button type="button" className="btn btn-primary" onClick={onClose}>
                        OK
                    </button>
                </div>
            </div>
        </div>
    );
};

export default NotificationModal;
