import React, { useState } from 'react';
import axios from 'axios';

const ScheduleAbsenceModal = ({ isOpen, onClose, username }) => {
    const [deactivationDate, setDeactivationDate] = useState('');
    const [reactivationDate, setReactivationDate] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    if (!isOpen) return null;

    const handleSubmit = (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccessMessage('');

        axios.post(`/api/schedule_absence/${username}`, {
            deactivation_date: deactivationDate,
            reactivation_date: reactivationDate,
        })
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
        setDeactivationDate('');
        setReactivationDate('');
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
                    <h5 className="modal-title">Agendar Ausência: {username}</h5>
                    <button type="button" className="btn-close" onClick={handleClose}></button>
                </div>
                <form onSubmit={handleSubmit}>
                    <div className="modal-body">
                        {error && <div className="alert alert-danger">{error}</div>}
                        {successMessage && <div className="alert alert-success">{successMessage}</div>}

                        <div className="mb-3">
                            <label htmlFor="deactivation_date" className="form-label">Data de Desativação</label>
                            <input
                                type="date"
                                id="deactivation_date"
                                className="form-control"
                                value={deactivationDate}
                                onChange={(e) => setDeactivationDate(e.target.value)}
                                required
                            />
                        </div>

                        <div className="mb-3">
                            <label htmlFor="reactivation_date" className="form-label">Data de Reativação</label>
                            <input
                                type="date"
                                id="reactivation_date"
                                className="form-control"
                                value={reactivationDate}
                                onChange={(e) => setReactivationDate(e.target.value)}
                                required
                            />
                        </div>
                    </div>
                    <div className="modal-footer">
                        <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={isLoading}>
                            Cancelar
                        </button>
                        <button type="submit" className="btn btn-primary" disabled={isLoading}>
                            {isLoading ? 'Agendando...' : 'Agendar'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default ScheduleAbsenceModal;
