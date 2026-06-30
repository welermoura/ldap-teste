import logging
import requests
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

# Desabilita avisos de certificados SSL autoassinados
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ZimbraSOAPClient:
    def __init__(self, url, admin_user, admin_password):
        self.url = url
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.auth_token = None

    def _send_soap_request(self, body_xml, timeout=15):
        """
        Método auxiliar para enviar uma requisição SOAP genérica para a API do Zimbra.
        """
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8"
        }
        
        # Constrói o cabeçalho de autenticação se houver token
        header_xml = ""
        if self.auth_token:
            header_xml = f"""
            <context xmlns="urn:zimbra">
                <authToken>{escape(self.auth_token)}</authToken>
            </context>
            """
            
        soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
            <soap:Header>
                {header_xml}
            </soap:Header>
            <soap:Body>
                {body_xml}
            </soap:Body>
        </soap:Envelope>
        """
        
        try:
            response = requests.post(self.url, data=soap_envelope.encode('utf-8'), headers=headers, timeout=timeout, verify=False)
            
            # Parse do XML retornado se o status for 200 ou 500 (SOAP Faults usam 500)
            if response.status_code in [200, 500]:
                try:
                    root = ET.fromstring(response.content)
                    
                    # namespaces comuns
                    soap_ns = "http://www.w3.org/2003/05/soap-envelope"
                    zimbra_ns = "urn:zimbra"
                    
                    # Verifica se há falhas SOAP
                    body = root.find(f"{{{soap_ns}}}Body")
                    if body is not None:
                        fault = body.find(f"{{{soap_ns}}}Fault")
                        if fault is not None:
                            reason_el = fault.find(f"{{{soap_ns}}}Reason")
                            reason_text = "Erro SOAP desconhecido"
                            if reason_el is not None:
                                text_el = reason_el.find(f"{{{soap_ns}}}Text")
                                if text_el is not None and text_el.text:
                                    reason_text = text_el.text
                            
                            # Tenta pegar código de erro específico do Zimbra
                            detail = fault.find(f"{{{soap_ns}}}Detail")
                            if detail is not None:
                                error_code = detail.find(f"{{{zimbra_ns}}}Error")
                                if error_code is not None:
                                    code_val = error_code.find(f"{{{zimbra_ns}}}Code")
                                    if code_val is not None and code_val.text:
                                        reason_text = f"[{code_val.text}] {reason_text}"
                                        
                            raise Exception(reason_text)
                    
                    if response.status_code == 200:
                        return root
                except ET.ParseError:
                    pass # Se não for XML válido, deixa raise_for_status tratar
                    
            response.raise_for_status()
            return ET.fromstring(response.content)
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro de conexão com o servidor Zimbra: {e}")
            raise Exception(f"Erro de conexão com o Zimbra: {str(e)}")

    def authenticate(self):
        """
        Autentica o administrador e obtém o authToken de sessão.
        """
        body_xml = f"""
        <AuthRequest xmlns="urn:zimbraAdmin">
            <name>{escape(self.admin_user)}</name>
            <password>{escape(self.admin_password)}</password>
        </AuthRequest>
        """
        
        # Limpa o token para forçar autenticação direta
        self.auth_token = None
        
        root = self._send_soap_request(body_xml)
        
        # Encontra o authToken na resposta
        body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
        if body is not None:
            auth_response = body.find("{urn:zimbraAdmin}AuthResponse")
            if auth_response is not None:
                token_el = auth_response.find("{urn:zimbraAdmin}authToken")
                if token_el is not None and token_el.text:
                    self.auth_token = token_el.text.strip()
                    return self.auth_token
                    
        raise Exception("Autenticação bem-sucedida, mas nenhum token foi retornado pelo Zimbra.")

    def get_domains(self):
        """
        Obtém a lista de domínios corporativos no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        body_xml = """
        <GetAllDomainsRequest xmlns="urn:zimbraAdmin">
        </GetAllDomainsRequest>
        """
        
        root = self._send_soap_request(body_xml)
        domains = []
        
        body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
        if body is not None:
            domains_response = body.find("{urn:zimbraAdmin}GetAllDomainsResponse")
            if domains_response is not None:
                for domain_el in domains_response.findall("{urn:zimbraAdmin}domain"):
                    domain_name = domain_el.attrib.get("name")
                    if domain_name:
                        domains.append({
                            "name": domain_name,
                            "id": domain_el.attrib.get("id")
                        })
                        
        return sorted(domains, key=lambda d: d["name"].lower())

    def get_dl_members(self, dl_email):
        """
        Obtém os membros de uma Lista de Distribuição específica no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        body_xml = f"""
        <GetDistributionListRequest xmlns="urn:zimbraAdmin">
            <dl by="name">{escape(dl_email)}</dl>
        </GetDistributionListRequest>
        """
        
        root = self._send_soap_request(body_xml)
        members = []
        dl_id = None
        dl_real_email = dl_email
        
        body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
        if body is not None:
            dl_response = body.find("{urn:zimbraAdmin}GetDistributionListResponse")
            if dl_response is not None:
                dl_el = dl_response.find("{urn:zimbraAdmin}dl")
                if dl_el is not None:
                    dl_id = dl_el.attrib.get("id")
                    dl_real_email = dl_el.attrib.get("name") or dl_email
                    
                    # Extrai os membros da DL
                    for dlm_el in dl_el.findall("{urn:zimbraAdmin}dlm"):
                        if dlm_el.text:
                            members.append(dlm_el.text.strip().lower())
                            
        return {
            "id": dl_id,
            "email": dl_real_email,
            "members": members
        }

    def add_dl_member(self, dl_email, member_email):
        """
        Adiciona um endereço de e-mail a uma Lista de Distribuição no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        # Resolve e-mail para ID caso seja fornecido o e-mail em vez do ID
        if "@" in dl_email:
            dl_info = self.get_dl_members(dl_email)
            dl_id = dl_info["id"]
        else:
            dl_id = dl_email

        body_xml = f"""
        <AddDistributionListMemberRequest xmlns="urn:zimbraAdmin">
            <id>{escape(dl_id)}</id>
            <dlm>{escape(member_email)}</dlm>
        </AddDistributionListMemberRequest>
        """
        
        self._send_soap_request(body_xml)
        return True

    def remove_dl_member(self, dl_email, member_email):
        """
        Remove um endereço de e-mail de uma Lista de Distribuição no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        # Resolve e-mail para ID caso seja fornecido o e-mail em vez do ID
        if "@" in dl_email:
            dl_info = self.get_dl_members(dl_email)
            dl_id = dl_info["id"]
        else:
            dl_id = dl_email

        body_xml = f"""
        <RemoveDistributionListMemberRequest xmlns="urn:zimbraAdmin">
            <id>{escape(dl_id)}</id>
            <dlm>{escape(member_email)}</dlm>
        </RemoveDistributionListMemberRequest>
        """
        
        self._send_soap_request(body_xml)
        return True

    def add_dl_alias(self, dl_email, alias_email):
        """
        Adiciona um apelido (alias) a uma Lista de Distribuição no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        # Busca o ID da lista pelo e-mail
        dl_info = self.get_dl_members(dl_email)
        dl_id = dl_info.get("id")
        if not dl_id:
            raise Exception(f"Lista de distribuição '{dl_email}' não encontrada no Zimbra.")
        body_xml = f"""
        <AddDistributionListAliasRequest xmlns="urn:zimbraAdmin" id="{escape(dl_id)}" alias="{escape(alias_email)}" />
        """
        self._send_soap_request(body_xml)
        return True

    def create_dl(self, dl_email):
        """
        Cria uma nova Lista de Distribuição no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        body_xml = f"""
        <CreateDistributionListRequest xmlns="urn:zimbraAdmin">
            <name>{escape(dl_email)}</name>
        </CreateDistributionListRequest>
        """
        
        self._send_soap_request(body_xml)
        return True

    def rename_dl(self, dl_email, new_dl_email):
        """
        Renomeia uma Lista de Distribuição no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        # Busca o ID da lista pelo e-mail atual
        dl_info = self.get_dl_members(dl_email)
        dl_id = dl_info.get("id")
        if not dl_id:
            raise Exception(f"Lista de distribuição '{dl_email}' não encontrada no Zimbra.")
            
        body_xml = f"""
        <RenameDistributionListRequest xmlns="urn:zimbraAdmin">
            <id>{escape(dl_id)}</id>
            <newName>{escape(new_dl_email)}</newName>
        </RenameDistributionListRequest>
        """
        
        self._send_soap_request(body_xml)
        return True

    def delete_dl(self, dl_email):
        """
        Exclui uma Lista de Distribuição no Zimbra.
        """
        if not self.auth_token:
            self.authenticate()
            
        # Busca o ID da lista pelo e-mail atual
        dl_info = self.get_dl_members(dl_email)
        dl_id = dl_info.get("id")
        if not dl_id:
            raise Exception(f"Lista de distribuição '{dl_email}' não encontrada no Zimbra.")
            
        body_xml = f"""
        <DeleteDistributionListRequest xmlns="urn:zimbraAdmin">
            <id>{escape(dl_id)}</id>
        </DeleteDistributionListRequest>
        """
        
        self._send_soap_request(body_xml)
        return True

    def get_all_dls(self):
        """
        Obtém todas as Listas de Distribuição no Zimbra, incluindo os seus apelidos (aliases).
        """
        if not self.auth_token:
            self.authenticate()
            
        body_xml = """
        <GetAllDistributionListsRequest xmlns="urn:zimbraAdmin">
        </GetAllDistributionListsRequest>
        """
        
        root = self._send_soap_request(body_xml)
        dls = []
        
        body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
        if body is not None:
            dls_response = body.find("{urn:zimbraAdmin}GetAllDistributionListsResponse")
            if dls_response is not None:
                for dl_el in dls_response.findall("{urn:zimbraAdmin}dl"):
                    dl_name = dl_el.attrib.get("name")
                    if dl_name:
                        # Extrai apelidos (aliases) da lista
                        aliases = []
                        for a_el in dl_el.findall("{urn:zimbraAdmin}a"):
                            if a_el.attrib.get("n") == "zimbraMailAlias" and a_el.text:
                                aliases.append(a_el.text.strip().lower())
                        dls.append({
                            "name": dl_name,
                            "id": dl_el.attrib.get("id"),
                            "aliases": aliases
                        })
                        
        return sorted(dls, key=lambda d: d["name"].lower())

    def get_account_info(self, account_email):
        """
        Obtém as informações de uma conta (mailbox) no Zimbra pelo e-mail ou alias.
        Retorna um dicionário contendo:
        - 'email': E-mail principal da conta
        - 'aliases': Lista de aliases (apelidos) da conta
        - 'status': Status da conta
        """
        if not self.auth_token:
            self.authenticate()
            
        body_xml = f"""
        <GetAccountRequest xmlns="urn:zimbraAdmin">
            <account by="name">{escape(account_email)}</account>
        </GetAccountRequest>
        """
        try:
            root = self._send_soap_request(body_xml)
            body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
            if body is not None:
                resp = body.find("{urn:zimbraAdmin}GetAccountResponse")
                if resp is not None:
                    acc_el = resp.find("{urn:zimbraAdmin}account")
                    if acc_el is not None:
                        name = acc_el.attrib.get("name")
                        aliases = []
                        status = "active"
                        for a_el in acc_el.findall("{urn:zimbraAdmin}a"):
                            n_attr = a_el.attrib.get("n")
                            if n_attr == "zimbraMailAlias" and a_el.text:
                                aliases.append(a_el.text.strip().lower())
                            elif n_attr == "zimbraAccountStatus" and a_el.text:
                                status = a_el.text.strip().lower()
                        return {
                            "email": name.strip().lower() if name else account_email.strip().lower(),
                            "aliases": aliases,
                            "status": status
                        }
        except Exception as e:
            logging.error(f"[ZIMBRA-API] Erro ao buscar conta '{account_email}': {e}")
        return None

    def search_accounts_with_forwarding(self):
        """
        Busca contas que tenham encaminhamento de e-mail ativo (zimbraPrefMailForwardingAddress=*)
        ou Reply-To configurado (zimbraPrefReplyToAddress=*) ou Notificação configurada (zimbraPrefNewMailNotificationAddress=*).
        """
        if not self.auth_token:
            self.authenticate()

        body_xml = """
        <SearchDirectoryRequest xmlns="urn:zimbraAdmin" types="accounts" limit="1000" query="(|(zimbraPrefMailForwardingAddress=*)(zimbraPrefReplyToAddress=*)(zimbraPrefNewMailNotificationAddress=*))" attrs="zimbraId,zimbraPrefMailForwardingAddress,zimbraPrefMailLocalDeliveryDisabled,zimbraPrefReplyToAddress,zimbraPrefNewMailNotificationAddress,displayName,cn,zimbraAccountStatus">
        </SearchDirectoryRequest>
        """
        
        try:
            root = self._send_soap_request(body_xml, timeout=90)
            body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
            accounts = []
            if body is not None:
                resp = body.find("{urn:zimbraAdmin}SearchDirectoryResponse")
                if resp is not None:
                    for acc_el in resp.findall("{urn:zimbraAdmin}account"):
                        acc_id = acc_el.attrib.get("id")
                        acc_name = acc_el.attrib.get("name")
                        
                        attrs = {
                            "id": acc_id,
                            "email": acc_name.strip().lower() if acc_name else "",
                            "forwarding_addresses": [],
                            "local_delivery_disabled": False,
                            "reply_to": "",
                            "notification_address": "",
                            "display_name": "",
                            "status": "active"
                        }
                        
                        for a_el in acc_el.findall("{urn:zimbraAdmin}a"):
                            n_attr = a_el.attrib.get("n")
                            val = a_el.text or ""
                            if n_attr == "zimbraPrefMailForwardingAddress":
                                if val:
                                    attrs["forwarding_addresses"].append(val.strip().lower())
                            elif n_attr == "zimbraPrefMailLocalDeliveryDisabled":
                                attrs["local_delivery_disabled"] = (val.strip().upper() == "TRUE")
                            elif n_attr == "zimbraPrefReplyToAddress":
                                if val:
                                    attrs["reply_to"] = val.strip().lower()
                            elif n_attr == "zimbraPrefNewMailNotificationAddress":
                                if val:
                                    attrs["notification_address"] = val.strip().lower()
                            elif n_attr == "displayName":
                                attrs["display_name"] = val.strip()
                            elif n_attr == "zimbraAccountStatus":
                                attrs["status"] = val.strip().lower()
                                
                        accounts.append(attrs)
            return accounts
        except Exception as e:
            logging.error(f"[ZIMBRA-API] Erro ao buscar contas com encaminhamento: {e}")
            raise e

    def remove_zimbra_attribute(self, account_id, attr_type):
        """
        Remove um atributo específico da conta (forwarding, reply_to ou notification).
        """
        if not self.auth_token:
            self.authenticate()

        if attr_type == 'forwarding':
            attrs_xml = """
            <a n="zimbraPrefMailForwardingAddress"></a>
            <a n="zimbraPrefMailLocalDeliveryDisabled">FALSE</a>
            """
        elif attr_type == 'reply_to':
            attrs_xml = """
            <a n="zimbraPrefReplyToAddress"></a>
            <a n="zimbraPrefReplyToDisplay"></a>
            <a n="zimbraPrefReplyToEnabled">FALSE</a>
            """
        elif attr_type == 'notification':
            attrs_xml = """
            <a n="zimbraPrefNewMailNotificationAddress"></a>
            <a n="zimbraPrefNewMailNotificationEnabled">FALSE</a>
            """
        else:
            raise Exception(f"Atributo desconhecido para remoção: {attr_type}")

        body_xml = f"""
        <ModifyAccountRequest xmlns="urn:zimbraAdmin">
            <id>{escape(account_id)}</id>
            {attrs_xml}
        </ModifyAccountRequest>
        """
        try:
            self._send_soap_request(body_xml)
            return True
        except Exception as e:
            logging.error(f"[ZIMBRA-API] Erro ao remover atributo '{attr_type}' da conta '{account_id}': {e}")
            raise e

    def modify_account(self, account_id, attrs):
        """
        Modifica atributos de uma conta via ModifyAccountRequest.
        `attrs` e um dict {nome_atributo: valor}, onde valor pode ser:
          - string: define o valor (string vazia limpa o atributo)
          - lista/tupla: define multiplos valores (lista vazia limpa o atributo)
        Ao limpar zimbraPrefMailForwardingAddress, reativa a entrega local
        para evitar que a conta deixe de receber mensagens.
        """
        if not self.auth_token:
            self.authenticate()

        attrs_xml = ""
        for name, value in attrs.items():
            if isinstance(value, (list, tuple)):
                if not value:
                    attrs_xml += f'<a n="{escape(name)}"></a>'
                else:
                    for v in value:
                        attrs_xml += f'<a n="{escape(name)}">{escape(str(v))}</a>'
            else:
                if value is None or value == '':
                    attrs_xml += f'<a n="{escape(name)}"></a>'
                else:
                    attrs_xml += f'<a n="{escape(name)}">{escape(str(value))}</a>'

        # Seguranca: se o encaminhamento foi totalmente removido, garante entrega local
        fwd = attrs.get('zimbraPrefMailForwardingAddress')
        if fwd is not None and (fwd == '' or (isinstance(fwd, (list, tuple)) and not fwd)):
            attrs_xml += '<a n="zimbraPrefMailLocalDeliveryDisabled">FALSE</a>'

        body_xml = f"""
        <ModifyAccountRequest xmlns="urn:zimbraAdmin">
            <id>{escape(account_id)}</id>
            {attrs_xml}
        </ModifyAccountRequest>
        """
        try:
            self._send_soap_request(body_xml)
            return True
        except Exception as e:
            logging.error(f"[ZIMBRA-API] Erro ao modificar conta '{account_id}': {e}")
            raise e

