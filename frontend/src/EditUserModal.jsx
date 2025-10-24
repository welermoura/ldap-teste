import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './EditUserModal.css';

const EditUserModal = ({ isOpen, onClose, username }) => {
    // Estado para os dados do formulário
    const [formData, setFormData] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    useEffect(() => {
        if (isOpen && username) {
            setIsLoading(true);
            setError('');
            setSuccessMessage('');
            axios.get(`/api/user_details/${username}`)
                .then(response => {
                    setFormData(response.data || {});
                })
                .catch(err => {
                    setError('Não foi possível carregar os dados do usuário.');
                    console.error("Erro ao buscar detalhes do usuário:", err);
                })
                .finally(() => {
                    setIsLoading(false);
                });
        }
    }, [isOpen, username]);

    const handleClose = () => {
        setFormData({});
        setError('');
        setSuccessMessage('');
        onClose();
    };

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccessMessage('');

        axios.post(`/api/edit_user/${username}`, formData)
            .then(response => {
                if (response.data.success) {
                    setSuccessMessage('Usuário atualizado com sucesso!');
                    // Fecha o modal após 2 segundos em caso de sucesso
                    setTimeout(() => {
                        handleClose();
                    }, 2000);
                } else {
                    setError(response.data.error || 'Ocorreu um erro desconhecido.');
                }
            })
            .catch(err => {
                setError(err.response?.data?.error || 'Falha na comunicação com o servidor.');
                console.error("Erro ao salvar alterações:", err);
            })
            .finally(() => {
                setIsLoading(false);
            });
    };

    if (!isOpen) {
        return null;
    }

    // Mapeamento para labels do formulário
    const fieldLabels = {
        givenName: 'Nome', sn: 'Sobrenome', initials: 'Iniciais',
        displayName: 'Nome de Exibição', description: 'Descrição', physicalDeliveryOfficeName: 'Escritório',
        telephoneNumber: 'Telefone Principal', mail: 'E-mail', wWWHomePage: 'Página da Web',
        streetAddress: 'Rua', postOfficeBox: 'Caixa Postal', l: 'Cidade',
        st: 'Estado/Província', postalCode: 'CEP', homePhone: 'Telefone Residencial',
        pager: 'Pager', mobile: 'Celular', facsimileTelephoneNumber: 'Fax',
        title: 'Cargo', department: 'Departamento', company: 'Empresa'
    };

    return (
        <div className="modal-backdrop">
            <div className="modal-content">
                <div className="modal-header">
                    <h5 className="modal-title">Editar Usuário: {username}</h5>
                    <button type="button" className="btn-close" onClick={handleClose}></button>
                </div>
                <div className="modal-body">
                    {isLoading && !Object.keys(formData).length > 0 && <p>Carregando...</p>}
                    {error && <div className="alert alert-danger">{error}</div>}
                    {successMessage && <div className="alert alert-success">{successMessage}</div>}

                    {Object.keys(formData).length > 0 && (
                        <form id="editUserForm" onSubmit={handleSubmit}>
                            <div className="row">
                                {Object.keys(fieldLabels).map(key => (
                                    <div className="col-md-6 mb-3" key={key}>
                                        <label htmlFor={key} className="form-label">{fieldLabels[key]}</label>
                                        <input
                                            type="text"
                                            id={key}
                                            name={key}
                                            className="form-control"
                                            value={formData[key] || ''}
                                            onChange={handleChange}
                                        />
                                    </div>
                                ))}
                            </div>
                        </form>
                    )}
                </div>
                <div className="modal-footer">
                    <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={isLoading}>Cancelar</button>
                    <button type="submit" form="editUserForm" className="btn btn-primary" disabled={isLoading}>
                        {isLoading ? 'Salvando...' : 'Salvar Alterações'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default EditUserModal;
