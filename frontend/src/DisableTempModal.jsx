import React, { useState } from 'react';
import axios from 'axios';

const DisableTempModal = ({ isOpen, onClose, username }) => {
    const [days, setDays] = useState(7);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    if (!isOpen) return null;

    const handleSubmit = (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccessMessage('');

        axios.post(`/api/disable_user_temp/${username}`, { days: parseInt(days, 10) })
            .then(response => {
                setSuccessMessage(response.data.message);
                setTimeout(() => {
                    onClose();
                    resetState();
                }, 2000);
            })
            .catch(err => {
                setError(err.response?.data?.error || 'Falha na comunicação.');
            })
            .finally(() => {
                setIsLoading(false);
            });
    };

    const resetState = () => {
        setDays(7);
        setIsLoading(false);
        setError('');
        setSuccessMessage('');
    };

    const handleClose = () => {
        resetState();
        onClose();
    };

    return (
        <div className="modal-backdrop">
            <div className="modal-content" style={{width: '500px'}}>
                <div className="modal-header">
                    <h5 className="modal-title">Desativar Temporariamente: {username}</h5>
                    <button type="button" className="btn-close" onClick={handleClose}></button>
                </div>
                <form onSubmit={handleSubmit}>
                    <div className="modal-body">
                        {error && <div className="alert alert-danger">{error}</div>}
                        {successMessage && <div className="alert alert-success">{successMessage}</div>}

                        <div className="mb-3">
                            <label htmlFor="disable_days" className="form-label">
                                Desativar a conta por quantos dias?
                            </label>
                            <input
                                type="number"
                                id="disable_days"
                                className="form-control"
                                value={days}
                                onChange={(e) => setDays(e.target.value)}
                                min="1"
                                required
                            />
                        </div>
                        <p className="form-text">
                            A conta será desativada imediatamente e uma reativação será agendada.
                        </p>
                    </div>
                    <div className="modal-footer">
                        <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={isLoading}>
                            Cancelar
                        </button>
                        <button type="submit" className="btn btn-primary" disabled={isLoading}>
                            {isLoading ? 'Agendando...' : 'Confirmar e Desativar'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default DisableTempModal;
