import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './EditUserModal.css';

const EditUserModal = ({ isOpen, onClose, username }) => {
    const [formData, setFormData] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [activeTab, setActiveTab] = useState('details');
    const [userGroups, setUserGroups] = useState([]);
    const [groupSearchQuery, setGroupSearchQuery] = useState('');
    const [groupSearchResults, setGroupSearchResults] = useState([]);

    const tabsConfig = {
        details: { label: 'Detalhes' },
        memberOf: { label: 'Membro De' }
    };

    // Unifica todos os campos e seus labels para facilitar a renderização
    const allFields = {
        givenName: 'Nome', sn: 'Sobrenome', initials: 'Iniciais', displayName: 'Nome de Exibição',
        description: 'Descrição', physicalDeliveryOfficeName: 'Escritório', mail: 'E-mail', wWWHomePage: 'Página da Web',
        streetAddress: 'Rua', postOfficeBox: 'Caixa Postal', l: 'Cidade', st: 'Estado/Província', postalCode: 'CEP',
        telephoneNumber: 'Telefone Principal', homePhone: 'Telefone Residencial', pager: 'Pager', mobile: 'Celular', facsimileTelephoneNumber: 'Fax',
        title: 'Cargo', department: 'Departamento', company: 'Empresa'
    };

    const fetchUserDetails = () => {
        setIsLoading(true);
        axios.get(`/api/user_details/${username}`)
            .then(response => setFormData(response.data || {}))
            .catch(() => setError('Não foi possível carregar os dados do usuário.'))
            .finally(() => setIsLoading(false));
    };

    const fetchUserGroups = () => {
        axios.get(`/api/user_groups/${username}`)
            .then(response => setUserGroups(response.data))
            .catch(() => setError('Não foi possível carregar os grupos do usuário.'));
    };

    useEffect(() => {
        if (isOpen && username) {
            setError('');
            setSuccessMessage('');
            setActiveTab('details');
            setGroupSearchQuery('');
            setGroupSearchResults([]);

            fetchUserDetails();
            fetchUserGroups();
        }
    }, [isOpen, username]);

    // Lógica para Adicionar/Remover Grupos
    const handleAddGroup = (groupName) => {
        axios.post('/api/add_user_to_group', { username, group_name: groupName })
            .then(() => {
                fetchUserGroups(); // Recarrega a lista de grupos do usuário
                setGroupSearchQuery(''); // Limpa a busca
                setGroupSearchResults([]);
            })
            .catch(err => setError(err.response?.data?.error || 'Erro ao adicionar ao grupo.'));
    };

    const handleRemoveGroup = (groupName) => {
        axios.post('/api/remove_user_from_group', { username, group_name: groupName })
            .then(() => {
                fetchUserGroups(); // Apenas recarrega a lista
            })
            .catch(err => setError(err.response?.data?.error || 'Erro ao remover do grupo.'));
    };

    // Lógica de busca com debounce
    useEffect(() => {
        if (groupSearchQuery.length < 3) {
            setGroupSearchResults([]);
            return;
        }
        const debounceTimer = setTimeout(() => {
            axios.get(`/api/search_groups?q=${groupSearchQuery}&username=${username}`)
                .then(response => setGroupSearchResults(response.data))
                .catch(() => { /* Silencia erros de busca para não serem intrusivos */ });
        }, 500); // 500ms de delay

        return () => clearTimeout(debounceTimer);
    }, [groupSearchQuery, username]);

    const handleGroupSearchChange = (e) => {
        setGroupSearchQuery(e.target.value);
    };


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

    const renderDetailsTab = () => (
        <div className="row">
            {Object.entries(allFields).map(([key, label]) => (
                <div className="col-md-6 mb-3" key={key}>
                    <label htmlFor={key} className="form-label">{label}</label>
                    <input
                        type="text" id={key} name={key} className="form-control"
                        value={formData[key] || ''} onChange={handleChange}
                    />
                </div>
            ))}
        </div>
    );

    const renderGroupsTab = () => (
        <div>
            {/* Seção para adicionar novos grupos */}
            <div className="mb-4">
                <h5>Adicionar a um novo grupo</h5>
                <div className="input-group">
                    <input
                        type="text"
                        className="form-control"
                        placeholder="Digite para buscar um grupo..."
                        value={groupSearchQuery}
                        onChange={handleGroupSearchChange}
                    />
                </div>
                {groupSearchResults.length > 0 && (
                    <ul className="list-group mt-2 search-results-dropdown">
                        {groupSearchResults.map(group => (
                            <li key={group.cn} className="list-group-item d-flex justify-content-between align-items-center">
                                <span>
                                    <strong>{group.cn}</strong>
                                    <br />
                                    <small className="text-muted">{group.description}</small>
                                </span>
                                <button className="btn btn-sm btn-success" onClick={() => handleAddGroup(group.cn)}>
                                    <i className="fas fa-plus"></i> Adicionar
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            {/* Seção para listar os grupos atuais */}
            <div>
                <h5>Membro de</h5>
                {userGroups.length > 0 ? (
                    <ul className="list-group">
                        {userGroups.map(group => (
                            <li key={group.cn} className="list-group-item d-flex justify-content-between align-items-center">
                                <span>
                                    <strong>{group.cn}</strong>
                                    <br />
                                    <small className="text-muted">{group.description}</small>
                                </span>
                                <button className="btn btn-sm btn-danger" onClick={() => handleRemoveGroup(group.cn)}>
                                    <i className="fas fa-trash-alt"></i> Remover
                                </button>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p>O usuário não é membro de nenhum grupo.</p>
                )}
            </div>
        </div>
    );

    if (!isOpen) return null;

    return (
        <div className="modal-backdrop">
            <div className="modal-content large"> {/* Nova classe para modal maior */}
                <div className="modal-header">
                    <h5 className="modal-title">Editar Usuário: {username}</h5>
                    <button type="button" className="btn-close" onClick={handleClose}></button>
                </div>

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
                                {activeTab === 'details' && (
                                    <form id="editUserForm" onSubmit={handleSubmit}>
                                        {renderDetailsTab()}
                                    </form>
                                )}
                                {activeTab === 'memberOf' && renderGroupsTab()}
                            </div>
                        </>
                    )}
                </div>

                <div className="modal-footer">
                    <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={isLoading}>Cancelar</button>
                    {activeTab === 'details' && (
                        <button type="submit" form="editUserForm" className="btn btn-primary" disabled={isLoading}>
                            {isLoading ? 'Salvando...' : 'Salvar Alterações'}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default EditUserModal;
