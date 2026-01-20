import React from 'react';
import { Page, Text, View, Document, StyleSheet } from '@react-pdf/renderer';
import { buildMatrixLayout } from './layoutMatrixBuilder';

const styles = StyleSheet.create({
    page: {
        flexDirection: 'column',
        backgroundColor: '#FFFFFF',
        padding: 40,
    },
    header: {
        marginBottom: 20,
        borderBottomWidth: 1,
        borderBottomColor: '#E2E8F0',
        paddingBottom: 10,
    },
    title: {
        fontSize: 24,
        color: '#1E293B',
        marginBottom: 4,
    },
    subtitle: {
        fontSize: 14,
        color: '#64748B',
    },
    // Cover Styles
    coverContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    leaderCard: {
        width: 300,
        padding: 20,
        backgroundColor: '#F8FAFC',
        borderWidth: 2,
        borderColor: '#3B82F6',
        borderRadius: 8,
        alignItems: 'center',
    },
    leaderName: {
        fontSize: 18,
        fontWeight: 'bold',
        color: '#0F172A',
        marginBottom: 8,
    },
    leaderRole: {
        fontSize: 14,
        color: '#475569',
    },
    // Grid Styles
    gridContainer: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 15,
        justifyContent: 'flex-start',
    },
    gridCard: {
        width: '45%', // 2 cards per row usually, or calculate based on requirement
        marginBottom: 15,
        padding: 12,
        backgroundColor: '#FFFFFF',
        borderWidth: 1,
        borderColor: '#E2E8F0',
        borderRadius: 6,
    },
    cardName: {
        fontSize: 12,
        fontWeight: 'bold',
        color: '#0F172A',
    },
    cardRole: {
        fontSize: 10,
        color: '#64748B',
        marginTop: 2,
    },
    footer: {
        position: 'absolute',
        bottom: 30,
        right: 40,
        fontSize: 10,
        color: '#94A3B8',
    }
});

const OrganogramDocument = ({ data, scope }) => {
    const pages = buildMatrixLayout(data, scope);

    return (
        <Document>
            {pages.map((pageData, index) => (
                <Page key={index} size="A4" orientation="landscape" style={styles.page}>
                    <View style={styles.header}>
                        <Text style={styles.title}>
                            {pageData.type === 'cover' ? pageData.title : pageData.title}
                        </Text>
                        {pageData.subtitle && <Text style={styles.subtitle}>{pageData.subtitle}</Text>}
                    </View>

                    {pageData.type === 'cover' ? (
                        <View style={styles.coverContainer}>
                            <View style={styles.leaderCard}>
                                <Text style={styles.leaderName}>{pageData.leader.name}</Text>
                                <Text style={styles.leaderRole}>{pageData.leader.title}</Text>
                                <Text style={{ fontSize: 10, color: '#94A3B8', marginTop: 10 }}>{pageData.leader.department}</Text>
                            </View>
                        </View>
                    ) : (
                        <View style={styles.gridContainer}>
                            {pageData.items.map((item, idx) => (
                                <View key={idx} style={{
                                    ...styles.gridCard,
                                    width: '23%', // ~4 cards per row
                                    height: 80,
                                }}>
                                    <Text style={styles.cardName}>{item.name}</Text>
                                    <Text style={styles.cardRole}>{item.title}</Text>
                                    <Text style={{ fontSize: 9, color: '#94A3B8', marginTop: 4 }}>{item.department}</Text>
                                </View>
                            ))}
                        </View>
                    )}

                    <Text style={styles.footer} render={({ pageNumber, totalPages }) => (
                        `${pageNumber} / ${totalPages}`
                    )} fixed />
                </Page>
            ))}
        </Document>
    );
};

export default OrganogramDocument;
