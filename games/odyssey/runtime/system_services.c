/* Horizon services Bayonetta 3 reaches that TotK never did, answered in-process over IPC (ipc.c). Command numbers and
   layouts follow the public switchbrew descriptions. Unknown commands still stop the runtime with their id. */
#include "runtime.h"
#include "ipc.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <stdlib.h>

/* ---------- set: nn::settings ISettingsServer ---------- */
/* nn::settings::Language order -> language code (switchbrew "Settings services", LanguageCode). */
static const char *const language_codes[] = {
    "ja", "en-US", "fr", "de", "it", "es", "zh-CN", "ko", "nl", "pt", "ru", "zh-TW", "en-GB", "fr-CA", "es-419",
    "zh-Hans", "zh-Hant", "pt-BR",
};
enum { LANGUAGES = sizeof language_codes / sizeof *language_codes, REGION_USA = 1 };

static uint64_t code_of(unsigned language) {
    uint64_t v = 0;
    memcpy(&v, language_codes[language], strlen(language_codes[language]));
    return v;
}
/* Writes up to `room` codes into a guest out buffer; returns how many. */
static int32_t write_codes(uint64_t addr, uint64_t size) {
    uint64_t *out = ipc_guest(addr, size);
    int32_t n = 0;
    for (; n < LANGUAGES && (uint64_t)(n + 1) * 8 <= size; n++) out[n] = code_of((unsigned)n);
    return n;
}
static void settings_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: { uint64_t v = runtime_desired_language(); IPC_OUT(rs, v); return; }   /* GetLanguageCode */
    case 1: {                                                                    /* GetAvailableLanguageCodes (C buffer) */
        if (!rq->nc) runtime_fail("set GetAvailableLanguageCodes: no output buffer");
        int32_t n = write_codes(rq->c[0].addr, rq->c[0].size);
        rs->xout[rs->nxout++] = (IpcBuffer){rq->c[0].addr, (uint64_t)n * 8, 0};
        IPC_OUT(rs, n); return;
    }
    case 2: {                                                                    /* MakeLanguageCode(Language) */
        uint32_t language = IPC_ARG(rq, uint32_t, 0);
        if (language >= LANGUAGES) { fprintf(stderr, "[totk-set] MakeLanguageCode(%u)\n", language); runtime_fail("set MakeLanguageCode: unknown language"); }
        uint64_t v = code_of(language); IPC_OUT(rs, v); return;
    }
    case 3: case 6: { int32_t n = LANGUAGES; IPC_OUT(rs, n); return; }          /* GetAvailableLanguageCodeCount(2) */
    case 4: { int32_t v = REGION_USA; IPC_OUT(rs, v); return; }                   /* GetRegionCode */
    case 5: {                                                                    /* GetAvailableLanguageCodes2 (B buffer) */
        if (!rq->nb) runtime_fail("set GetAvailableLanguageCodes2: no output buffer");
        int32_t n = write_codes(rq->b[0].addr, rq->b[0].size); IPC_OUT(rs, n); return;
    }
    case 8: { uint8_t v = 0; IPC_OUT(rs, v); return; }                            /* GetQuestFlag: not a kiosk unit */
    default: ipc_unimplemented(s, rq);
    }
}

/* ---------- bsd:u: nn::socket, offline ---------- */
/* The game is played offline, as a Switch without a connection: the client registers and its monitor starts, but every
   socket it asks for fails with ENETDOWN. Commands return {s32 ret, u32 errno} (switchbrew "Sockets services"). */
enum { BSD_ENETDOWN = 50 };
static void bsd_result(IpcResponse *rs, int32_t ret, uint32_t err) { IPC_OUT(rs, ret); IPC_OUT(rs, err); }
static void bsd_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: { uint64_t pid = 0; IPC_OUT(rs, pid); return; }                         /* RegisterClient(config, tmem) */
    case 1: return;                                                               /* StartMonitoring(pid) */
    case 2: case 3:                                                               /* Socket / SocketExempt */
        fprintf(stderr, "[totk-net] socket(%u, %u, %u) refused: offline\n", IPC_ARG(rq, uint32_t, 0), IPC_ARG(rq, uint32_t, 4), IPC_ARG(rq, uint32_t, 8));
        bsd_result(rs, -1, BSD_ENETDOWN); return;
    default: ipc_unimplemented(s, rq);
    }
}

static void hid_resource_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){
    if(rq->cmd==0){rs->copy[rs->ncopy++]=runtime_ipc_new_shared_memory(0x40000);return;}
    ipc_unimplemented(s,rq);
}
static void hid_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){
    if(rq->cmd==0){rs->move[rs->nmove++]=runtime_ipc_new_session("IAppletResource",hid_resource_handler,NULL,NULL);return;}
    if(rq->cmd==1){if(rq->data_size!=12)runtime_fail("hid ActivateDebugPad arguments");return;}
    if(rq->cmd==124){if(rq->data_size!=20)runtime_fail("hid SetNpadJoyAssignmentModeDual arguments");return;}
    if(rq->cmd==300){if(rq->data_size!=12)runtime_fail("hid ActivateConsoleSixAxisSensor arguments");return;}
    if(rq->cmd==306){if(rq->data_size!=36||rq->ncopy+rq->nmove!=2)runtime_fail("hid InitializeSevenSixAxisSensor arguments");return;}
    ipc_unimplemented(s,rq);
}
static void friend_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){(void)rs;ipc_unimplemented(s,rq);}
static void friend_service_creator_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){
    if(rq->cmd!=0) { ipc_unimplemented(s,rq); }
    if(rq->data_size||rq->ncopy||rq->nmove||rq->na||rq->nb||rq->nw||rq->nc) runtime_fail("friend CreateFriendService arguments");
    rs->move[rs->nmove++]=runtime_ipc_new_session("IFriendService",friend_handler,NULL,NULL);
}
static void bcat_directory_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){(void)rs;ipc_unimplemented(s,rq);}
static void bcat_storage_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){
    if(rq->cmd!=10) { ipc_unimplemented(s,rq); }
    if(rq->data_size||rq->nx||rq->na||rq->nb!=1||rq->nw||rq->nc||rq->ncopy||rq->nmove||!rq->b[0].size) runtime_fail("bcat CreateDirectoryService arguments");
    rs->move[rs->nmove++]=runtime_ipc_new_session("IDeliveryCacheDirectoryService",bcat_directory_handler,NULL,NULL);
}
static void bcat_root_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){
    if(rq->cmd!=0&&rq->cmd!=1) { ipc_unimplemented(s,rq); }
    if(rq->data_size!=8||rq->nx||rq->na||rq->nb||rq->nw||rq->nc||rq->ncopy||rq->nmove) runtime_fail("bcat service creator arguments");
    const char *name=rq->cmd==0?"IBcatService":"IDeliveryCacheStorageService";
    rs->move[rs->nmove++]=runtime_ipc_new_session(name,bcat_storage_handler,NULL,NULL);
}
static void storage_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){(void)rs;ipc_unimplemented(s,rq);}
static void fsp_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs){
    (void)rs;
    if(rq->cmd==1006&&getenv("TOTK_IPC_DUMP")&&rq->na&&rq->a[0].size<=256){const unsigned char *p=ipc_guest(rq->a[0].addr,rq->a[0].size);fprintf(stderr,"[totk-ipc] fsp-srv 1006 A[%llu]:",(unsigned long long)rq->a[0].size);for(uint64_t i=0;i<rq->a[0].size;i++)fprintf(stderr," %02x",p[i]);fputc('\n',stderr);}
    if(rq->cmd==1){if(rq->data_size!=8||rq->ncopy||rq->nmove||rq->na||rq->nb||rq->nw||rq->nc)runtime_fail("fsp-srv Initialize arguments");return;}
    if(rq->cmd==1005){if(rq->data_size||rq->ncopy||rq->nmove||rq->na||rq->nb||rq->nw||rq->nc)runtime_fail("fsp-srv OpenDataStorageByCurrentProcess arguments");rs->move[rs->nmove++]=runtime_ipc_new_session("IStorage",storage_handler,NULL,NULL);return;}
    if(rq->cmd==1006){if(rq->data_size||rq->nx||rq->na!=1||rq->nb||rq->nw||rq->nc||rq->ncopy||rq->nmove||rq->a[0].size<16||rq->a[0].size>1024)runtime_fail("fsp-srv access log arguments");const char *p=ipc_guest(rq->a[0].addr,rq->a[0].size);if(memcmp(p,"FS_ACCESS: { ",13)||memcmp(p+rq->a[0].size-3," }\n",3))runtime_fail("fsp-srv access log format");return;}
    if(rq->cmd==1011){if(rq->data_size||rq->ncopy||rq->nmove||rq->na||rq->nb||rq->nw||rq->nc)runtime_fail("fsp-srv IsEnabledAccessLog arguments");uint32_t enabled=0;IPC_OUT(rs,enabled);return;}
    ipc_unimplemented(s,rq);
}

/* ---------- SDK functions answered by name (runtime_by3_override) ----------
   Network-facing libraries answer as a Switch without a connection. The failure results are generic ones of each
   library's module (nifm 110, ssl 123, account 124), not a specific console error: the game only needs "unavailable". */
#define RESULT(module, description) ((uint32_t)(module) | ((uint32_t)(description) << 9))
#define NIFM_UNAVAILABLE RESULT(110, 300)
#define NSD_UNAVAILABLE RESULT(122, 300)
#define SSL_UNAVAILABLE RESULT(123, 300)
#define NSA_UNAVAILABLE RESULT(124, 280)
static void nop(void) {}
static uint32_t ok(void) { return 0; }
static uint8_t network_available(void) { return 0; }
static uint32_t nifm_unavailable(void) { return NIFM_UNAVAILABLE; }
static uint32_t ssl_unavailable(void) { return SSL_UNAVAILABLE; }
static uint32_t nsd_resolve_unavailable(void *out, const void *fqdn) {
    (void)out;
    (void)fqdn;
    static int once;
    if (!once++) fprintf(stderr, "[totk-net] DNS lookup unavailable: offline\n");
    return NSD_UNAVAILABLE;
}
static uint32_t ssl_context_create(unsigned version) { (void)version; return SSL_UNAVAILABLE; }
static uint32_t ssl_import_server_pki(void *context, uint64_t *out, const void *data, uint32_t size, unsigned format) {
    (void)context;
    (void)out;
    (void)data;
    (void)size;
    (void)format;
    return SSL_UNAVAILABLE;
}
static uint32_t nsa_unavailable(void) { return NSA_UNAVAILABLE; }
static uint32_t friends_unavailable(void) { return RESULT(121, 300); }
static uint32_t nifm_request(void) { static int once; if (!once++) fprintf(stderr, "[totk-net] network request: offline\n"); return NIFM_UNAVAILABLE; }
static uint8_t nifm_request_on_hold(void) { return 0; }
static uint32_t nifm_primary_ip(void *out) { (void)out; return NIFM_UNAVAILABLE; }
static uint8_t inactivity_not_extended(void) { return 0; }
static uint8_t stereo_restriction_get(void) { return 0; }
static uint32_t stereo_restriction_set(unsigned char restricted) { (void)restricted; return 0; }
static uint32_t stereo_restriction_configurable(void) { return 0; }
static uint32_t stereo_restriction_permission(void) { return 0; }
static uint32_t home_button_inhibit(void) { return 0; }
static uint32_t nsa_available(unsigned char *available, const void *handle) {
    (void)handle;
    if (available) *available = 0;
    return 0;
}
static int64_t network_clock_now(void) { return (int64_t)time(NULL); }   /* time_point: seconds since the epoch */
static void environment_identifier(char *out) { if (!out) runtime_fail("nsd environment output"); memset(out, 0, 8); memcpy(out, "lp1", 3); }
static void execute_program(int index, const void *param, uint64_t size) {
    (void)param; fprintf(stderr, "[totk] nn::oe::ExecuteProgram(%d, %llu bytes)\n", index, (unsigned long long)size);
    runtime_fail("the game asked to start its program index 1 (title 01004A4010FEA001), which is not supported yet");
}
/* Open users kept across a program jump (PushOpenUsers before ExecuteProgram, PopOpenUsers in the next program). A
   fresh start has none; the game then opens its user the usual way (runtime/account.c). */
static void push_open_users(void) {}
static uint32_t pop_open_users(int32_t *count, void *handles, int32_t max) {
    (void)handles; (void)max; if (!count) runtime_fail("PopOpenUsers count pointer"); *count = 0; return 0;
}
void *runtime_by3_override(const char *name) {
    static const struct { const char *name; void *fn; } entries[] = {
        {"_ZN2nn2oe13MuteRecordingEv", nop}, {"_ZN2nn2oe15UnmuteRecordingEv", nop},
        {"_ZN2nn2oe15EnableRecordingEv", nop}, {"_ZN2nn2oe16DisableRecordingEv", nop},
        {"_ZN2nn2oe14ExecuteProgramEiPKvm", execute_program},
        {"_ZN2nn4nifm10InitializeEv", ok}, {"_ZN2nn4nifm18IsNetworkAvailableEv", network_available},
        {"_ZN2nn4nifm20SubmitNetworkRequestEv", nifm_request}, {"_ZN2nn4nifm27SubmitNetworkRequestAndWaitEv", nifm_request},
        {"_ZN2nn4nifm22IsNetworkRequestOnHoldEv", nifm_request_on_hold}, {"_ZN2nn4nifm26HandleNetworkRequestResultEv", nifm_unavailable},
        {"_ZN2nn4nifm20CancelNetworkRequestEv", nop},
        {"_ZN2nn4nifm31HandleNetworkRequestErrorResultEv", nifm_unavailable},
        {"_ZN2nn4nifm22GetCurrentProxySettingEPNS0_12ProxySettingE", nifm_unavailable},
        {"_ZN2nn4nifm26GetCurrentPrimaryIpAddressEP7in_addr", nifm_primary_ip},
        {"_ZN2nn4nifm26GetCurrentPrimaryIpAddressEPNS_6socket6InAddrE", nifm_unavailable},
        {"_ZN2nn3ssl10InitializeEv", ok}, {"_ZN2nn3ssl8FinalizeEv", ok},
        {"_ZN2nn3ssl7Context6CreateENS1_10SslVersionE", ssl_context_create},
        {"_ZN2nn3ssl7Context15ImportServerPkiEPmPKcjNS0_17CertificateFormatE", ssl_import_server_pki},
        {"_ZN2nn3ssl14BuiltInManager22GetBuiltInCertificatesEPPNS0_26BuiltInCertificateInfoBaseEPhjPNS0_15CaCertificateIdEj", ssl_unavailable},
        {"_ZN2nn3ssl14BuiltInManager28GetBuiltInCertificateBufSizeEPjPNS0_15CaCertificateIdEj", ssl_unavailable},
        {"_ZN2nn7account36EnsureNetworkServiceAccountAvailableERKNS0_10UserHandleE", nsa_unavailable},
        {"_ZN2nn7account32IsNetworkServiceAccountAvailableEPbRKNS0_10UserHandleE", nsa_available},
        {"_ZN2nn7account26GetNetworkServiceAccountIdEPNS0_23NetworkServiceAccountIdERKNS0_10UserHandleE", nsa_unavailable},
        {"_ZN2nn7account37LoadNetworkServiceAccountIdTokenCacheEPmPcmRKNS0_10UserHandleE", nsa_unavailable},
        {"_ZN2nn7account44EnsureNetworkServiceAccountIdTokenCacheAsyncEPNS0_12AsyncContextERKNS0_10UserHandleE", nsa_unavailable},
        {"_ZN2nn7friends12UserPresence10InitializeERKNS_7account3UidE", ok},
        {"_ZN2nn7friends10InitializeEv", ok},
        {"_ZN2nn7friends14GetProfileListEPNS0_12AsyncContextEPNS0_7ProfileEPKNS_7account23NetworkServiceAccountIdEi", friends_unavailable},
        {"_ZN2nn2oe37IsUserInactivityDetectionTimeExtendedEv", inactivity_not_extended},
        {"_ZN2nn2oe23BeginBlockingHomeButtonEv", home_button_inhibit},
        {"_ZN2nn2oe21EndBlockingHomeButtonEv", home_button_inhibit},
        {"_ZN2nn4pctl26GetStereoVisionRestrictionEv", stereo_restriction_get},
        {"_ZN2nn4pctl26SetStereoVisionRestrictionEb", stereo_restriction_set},
        {"_ZN2nn4pctl42ConfirmStereoVisionRestrictionConfigurableEv", stereo_restriction_configurable},
        {"_ZN2nn4pctl53RequestStereoVisionRestrictionConfigurationPermissionEv", stereo_restriction_permission},
        {"_ZN2nn3nsd9ResolveExEPNS0_4FqdnERKS1_", nsd_resolve_unavailable},
        {"_ZN2nn4time26StandardNetworkSystemClock3nowEv", network_clock_now},
        {"_ZN2nn3err21ReportMultimediaErrorENS_6ResultERKN5movie25MultimediaTelemetryReportE", nop},
        {"_ZN2nn3nsd24GetEnvironmentIdentifierEPNS0_21EnvironmentIdentifierE", environment_identifier},
        {"_ZN2nn5prepo10InitializeEv", nop},
        {"_ZN2nn3hid18StartSixAxisSensorERKNS0_19SixAxisSensorHandleE", nop},
        {"_ZN2nn7account13PushOpenUsersEv", push_open_users},
        {"_ZN2nn7account12PopOpenUsersEPiPNS0_10UserHandleEi", pop_open_users},
    };
    for (size_t i = 0; i < sizeof entries / sizeof *entries; i++) if (!strcmp(name, entries[i].name)) return entries[i].fn;
    return NULL;
}

__attribute__((constructor)) static void register_system_services(void) {
    /* Bayonetta 3 makes one 1348 MiB NVN memory pool at start; the shared graphics layer refuses zero-copy GPU buffers
       above 1 GiB unless told otherwise (nvn_mtl.m pool_buffer_max). A value the user set wins. */
    setenv("DM_POOL_BUFFER_MAX_MIB", "2048", 0);
    /* Present pacing as on the Switch: a 60 Hz base, the game's present interval on top (1 = 60 fps, 2 = 30 fps). The
       TotK host follows the display (120 Hz on ProMotion) and runs uncapped, which relies on TotK's real-time frame step
       patch; without it a game that advances per frame would run twice as fast. */
    setenv("DM_PRESENT_HZ", "60", 0);
    setenv("TOTK_UNCAPPED", "0", 0);
    /* It draws a depth pre-pass, then the colour pass with a LEQUAL test: positions must match bit for bit between the two
       (nvn_mtl.m totk_precise_opts, preserveInvariance). */
    setenv("DM_PRESERVE_INVARIANCE", "1", 0);
    /* Its shader binaries mix GLSLC GPU code versions (1.15 and 1.16 seen first); the graphics layer's measured driver
       table stops at 1.14. The layer reads only three control-section fields (code length, stage, compute group size)
       and stops on implausible values, so a newer layout would show at once. */
    setenv("DM_NVN_GPU_CODE_MAX_MINOR", "31", 0);
    runtime_ipc_register("set", settings_handler, NULL, NULL);
    runtime_ipc_register("bsd:u", bsd_handler, NULL, NULL);
    runtime_ipc_register("hid", hid_handler, NULL, NULL);
    runtime_ipc_register("friend:u", friend_service_creator_handler, NULL, NULL);
    runtime_ipc_register("bcat:u", bcat_root_handler, NULL, NULL);
    runtime_ipc_register("fsp-srv", fsp_handler, NULL, NULL);
}
