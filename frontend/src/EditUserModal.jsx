import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './EditUserModal.css';

const EditUserModal = ({ isOpen, onClose, username }) => {
    const [formData, setFormData] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [activeTab, setActiveTab] = useState('geral');

    // Mapeamento de campos para abas e labels
    const tabsConfig = {
        geral: {
            label: 'Geral',
            fields: {
                givenName: 'Nome', sn: 'Sobrenome', initials: 'Iniciais',
                displayName: 'Nome de Exibição', description: 'Descrição',
                physicalDeliveryOfficeName: 'Escritório', mail: 'E-mail', wWWHomePage: 'Página da Web',
            }
        },
        endereco: {
            label: 'Endereço',
            fields: {
                streetAddress: 'Rua', postOfficeBox: 'Caixa Postal', l: 'Cidade',
                st: 'Estado/Província', postalCode: 'CEP',
            }
        },
        telefones: {
            label: 'Telefones',
            fields: {
                telephoneNumber: 'Telefone Principal', homePhone: 'Telefone Residencial',
                pager: 'Pager', mobile: 'Celular', facsimileTelephoneNumber: 'Fax',
            }
        },
        organizacao: {
            label: 'Organização',
            fields: {
                title: 'Cargo', department: 'Departamento', company: 'Empresa',
            }
        }
    };

    useEffect(() => {
        if (isOpen && username) {
            setIsLoading(true);
            setError('');
            setSuccessMessage('');
            setActiveTab('geral');
            axios.get(`/api/user_details/${username}`)
                .then(response => {
                    setFormData(response.data || {});
                })
                .catch(() => {
                    setError('Não foi possível carregar os dados do usuário.');
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
                    setTimeout(handleClose, 2000);
                } else {
                    setError(response.data.error || 'Ocorreu um erro desconhecido.');
                }
            })
            .catch(err => {
                setError(err.response?.data?.error || 'Falha na comunicação com o servidor.');
            })
            .finally(() => {
                setIsLoading(false);
            });
    };

    const renderTabContent = () => {
        const activeTabData = tabsConfig[activeTab];
        if (!activeTabData) return null;

        return (
            <div className="row">
                {Object.entries(activeTabData.fields).map(([key, label]) => (
                    <div className="col-md-6 mb-3" key={key}>
                        <label htmlFor={key} className="form-label">{label}</label>
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
        );
    };

    if (!isOpen) return null;

    return (
        <div className="modal-backdrop">
            <div className="modal-content">
                <div className="modal-header">
                    <h5 className="modal-title">Editar Usuário: {username}</h5>
                    <button type="button" className="btn-close" onClick={handleClose}></button>
                </div>
                <form id="editUserForm" onSubmit={handleSubmit}>
                    <div className="modal-body">
                        {isLoading && !Object.keys(formData).length > 0 && <p>Carregando...</p>}
                        {error && <div className="alert alert-danger">{error}</div>}
                        {successMessage && <div className="alert alert-success">{successMessage}</div>}

                        {Object.keys(formData).length > 0 && (
                            <>
                                <ul className="nav nav-tabs">
                                    {Object.entries(tabsConfig).map(([key, { label }]) => (
                                        <li className="nav-item" key={key}>
                                            <button
                                                className={`nav-link ${activeTab === key ? 'active' : ''}`}
                                                type="button"
                                                onClick={() => setActiveTab(key)}
                                            >
                                                {label}
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                                <div className="tab-content p-3">
                                    {renderTabContent()}
                                </div>
                            </>
                        )}
                    </div>
                    <div className="modal-footer">
                        <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={isLoading}>Cancelar</button>
                        <button type="submit" className="btn btn-primary" disabled={isLoading}>
                            {isLoading ? 'Salvando...' : 'Salvar Alterações'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default EditUserModal;
