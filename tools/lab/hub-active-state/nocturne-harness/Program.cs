// Lab harness for tools/lab/hub-active-state: Nocturne's answer to "what is active at t" for the
// lab's synthetic records. Synthetic data only.
//
// Usage: dotnet run -- <cases.json> [--mock-dedup]  (run.sh builds it inside a Nocturne tree)
//
// Real Nocturne code exercised, per case on a fresh SQLite database built by Nocturne's own test
// fixture (TestDbContextFactory.CreateSqliteWithTenant, as StateSpanRepositoryTests does):
//   TreatmentDecomposer.DecomposeAsync        Profile Switch / Temporary Override / Temporary Target
//                                             -> StateSpan
//   DeviceStatusDecomposer.DecomposeAsync     devicestatus.override -> Override StateSpan
//   ProfileDecomposer.DecomposeAsync          profile document -> V4 schedules
//   StateSpanService + StateSpanRepository    upsert, supersession, GetActiveAtAsync, GetStateSpansAsync
//   DeduplicationService                      the real one (unless --mock-dedup)
//   ActiveProfileResolver, BasalRateResolver  (internal; constructed by reflection)
//   V4 schedule repositories, PatientRecordRepository, TestTenantDbContextFactory
// Mocked (not on the state-span path): bolus/carb/BG/note/device-event/temp-basal/APS/pump/
// uploader/extras repositories, device service, food service, insulin repository, audit context.
// Each record is sent through the decomposer on its own, in the case's arrival order, as a
// separate upload would be.

using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Nocturne.API.Services.Glucose;
using Nocturne.API.Services.V4;
using Nocturne.Core.Contracts.Audit;
using Nocturne.Core.Contracts.Devices;
using Nocturne.Core.Contracts.Glucose;
using Nocturne.Core.Contracts.Infrastructure;
using Nocturne.Core.Contracts.Multitenancy;
using Nocturne.Core.Contracts.Profiles.Resolvers;
using Nocturne.Core.Contracts.Treatments;
using Nocturne.Core.Contracts.V4;
using Nocturne.Core.Contracts.V4.Repositories;
using Nocturne.Core.Models;
using Nocturne.Infrastructure.Data;
using Nocturne.Infrastructure.Data.Repositories;
using Nocturne.Infrastructure.Data.Repositories.V4;
using Nocturne.Infrastructure.Data.Services;
using Nocturne.Tests.Shared.Infrastructure;

if (args.Length < 1)
{
    Console.Error.WriteLine("usage: HubActiveState <cases.json> [--mock-dedup]");
    return 2;
}

var mockDedup = args.Contains("--mock-dedup");
var root = JsonNode.Parse(await File.ReadAllTextAsync(args[0]))!;
var profileJson = root["profile"]!.ToJsonString();
var outCases = new JsonArray();

foreach (var c in root["cases"]!.AsArray())
{
    outCases.Add(await RunCase(c!, profileJson, mockDedup));
}

var output = new JsonObject
{
    ["hub"] = "nocturne",
    ["dedup"] = mockDedup ? "mocked" : "DeduplicationService",
    ["cases"] = outCases,
};
Console.Out.Write(output.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
return 0;

static async Task<JsonObject> RunCase(JsonNode c, string profileJson, bool mockDedup)
{
    var tenantId = Guid.Parse("00000000-0000-0000-0000-00000000a001");
    using var db = TestDbContextFactory.CreateSqliteWithTenant(tenantId, "lab");
    await using var ctx = db.CreateContext();
    var audit = Mock.Of<IAuditContext>();
    ctx.AuditContext = audit;

    var tenant = new Mock<ITenantAccessor>();
    tenant.Setup(t => t.TenantId).Returns(tenantId);
    tenant.Setup(t => t.IsResolved).Returns(true);

    var sp = new ServiceCollection().BuildServiceProvider();
    IDeduplicationService dedup = mockDedup
        ? Mock.Of<IDeduplicationService>()
        : new DeduplicationService(ctx, sp.GetRequiredService<IServiceScopeFactory>(),
            NullLogger<DeduplicationService>.Instance, tenant.Object);

    var spanRepo = new StateSpanRepository(ctx, dedup, audit, NullLogger<StateSpanRepository>.Instance);
    var spans = new StateSpanService(spanRepo, NullLogger<StateSpanService>.Instance);

    var factory = new TestTenantDbContextFactory(ctx);
    var therapy = new TherapySettingsRepository(factory, audit, NullLogger<TherapySettingsRepository>.Instance);
    var basal = new BasalScheduleRepository(factory, audit, NullLogger<BasalScheduleRepository>.Instance);
    var carbRatio = new CarbRatioScheduleRepository(factory, audit, NullLogger<CarbRatioScheduleRepository>.Instance);
    var sens = new SensitivityScheduleRepository(factory, audit, NullLogger<SensitivityScheduleRepository>.Instance);
    var target = new TargetRangeScheduleRepository(factory, audit, NullLogger<TargetRangeScheduleRepository>.Instance);
    var patientRecords = new PatientRecordRepository(factory, NullLogger<PatientRecordRepository>.Instance);
    var profileDecomposer = new ProfileDecomposer(therapy, basal, carbRatio, sens, target, NullLogger<ProfileDecomposer>.Instance);

    var cache = new MemoryCache(new MemoryCacheOptions());
    var apiAsm = typeof(TreatmentDecomposer).Assembly;
    var activeProfile = (IActiveProfileResolver)Construct(apiAsm,
        "Nocturne.API.Services.Profiles.Resolvers.ActiveProfileResolver",
        spans, tenant.Object, cache);
    var basalRate = (IBasalRateResolver)Construct(apiAsm,
        "Nocturne.API.Services.Profiles.Resolvers.BasalRateResolver",
        basal, therapy, patientRecords, activeProfile, tenant.Object, cache);

    var treatmentDecomposer = new TreatmentDecomposer(
        ctx,
        Mock.Of<IBolusRepository>(), Mock.Of<ITempBasalRepository>(), Mock.Of<ICarbIntakeRepository>(),
        Mock.Of<IBGCheckRepository>(), Mock.Of<INoteRepository>(), Mock.Of<IDeviceEventRepository>(),
        Mock.Of<IBolusCalculationRepository>(),
        spans,
        Mock.Of<ITreatmentFoodService>(), Mock.Of<IDeviceService>(), Mock.Of<IPatientDeviceStamper>(),
        profileDecomposer, activeProfile, Mock.Of<IPatientInsulinRepository>(),
        audit, NullLogger<TreatmentDecomposer>.Instance);

    var deviceStatusDecomposer = new DeviceStatusDecomposer(
        Mock.Of<IApsSnapshotRepository>(), Mock.Of<IPumpSnapshotRepository>(),
        Mock.Of<IUploaderSnapshotRepository>(), Mock.Of<IDeviceStatusExtrasRepository>(),
        spans, Mock.Of<IDeviceService>(), audit, NullLogger<DeviceStatusDecomposer>.Instance);

    var writes = new JsonArray();

    // The profile document first, as every case's fixture.
    var profile = JsonSerializer.Deserialize<Profile>(profileJson)!;
    var pr = await profileDecomposer.DecomposeAsync(profile, WriteOrigin.Live);
    writes.Add(new JsonObject { ["id"] = profile.Id, ["collection"] = "profile", ["created"] = pr.CreatedRecords.Count, ["error"] = null });

    foreach (var r in c["records"]!.AsArray())
    {
        var collection = (string)r!["collection"]!;
        var docJson = r["doc"]!.ToJsonString();
        var w = new JsonObject { ["id"] = (string?)r["doc"]!["_id"], ["collection"] = collection };
        try
        {
            V4DecompositionCount result;
            if (collection == "treatments")
            {
                var t = JsonSerializer.Deserialize<Treatment>(docJson)!;
                var res = await treatmentDecomposer.DecomposeAsync(t, WriteOrigin.Live);
                result = new(res.CreatedRecords.Count, res.UpdatedRecords.Count,
                    res.CreatedRecords.Select(o => o?.GetType().Name ?? "null (mocked repository)").ToList());
            }
            else
            {
                var ds = JsonSerializer.Deserialize<DeviceStatus>(docJson)!;
                var res = await deviceStatusDecomposer.DecomposeAsync(ds, WriteOrigin.Live);
                result = new(res.CreatedRecords.Count, res.UpdatedRecords.Count,
                    res.CreatedRecords.Select(o => o?.GetType().Name ?? "null (mocked repository)").ToList());
            }
            w["created"] = result.Created;
            w["updated"] = result.Updated;
            w["createdTypes"] = new JsonArray(result.Types.Select(x => (JsonNode)x).ToArray());
            w["error"] = null;
        }
        catch (Exception ex)
        {
            w["error"] = ex.GetType().Name + ": " + ex.Message;
            w["at"] = ex.StackTrace?.Split('\n').FirstOrDefault()?.Trim();
        }
        writes.Add(w);
    }

    var asks = c["asks"]!.AsArray().Select(a => (string)a!).ToHashSet();
    var queries = new JsonArray();
    foreach (var q in c["queries"]!.AsArray())
    {
        var tIso = (string)q!["t"]!;
        var at = DateTimeOffset.Parse(tIso).UtcDateTime;
        var mills = new DateTimeOffset(at, TimeSpan.Zero).ToUnixTimeMilliseconds();
        var answers = new JsonObject();

        if (asks.Contains("tt"))
            answers["tt"] = await SpanAnswer(spanRepo, spans, StateSpanCategory.TemporaryTarget, at, "Active");
        if (asks.Contains("override_tx"))
            answers["override_tx"] = await SpanAnswer(spanRepo, spans, StateSpanCategory.Override, at, null);
        if (asks.Contains("override_ds"))
        {
            var a = await SpanAnswer(spanRepo, spans, StateSpanCategory.Override, at, null);
            a["key"] = (string)a["key"]! == "none" ? "none" : "active";
            answers["override_ds"] = a;
        }
        if (asks.Contains("profile"))
        {
            var name = await activeProfile.GetActiveProfileNameAsync(mills);
            var adj = await activeProfile.GetCircadianAdjustmentAsync(mills);
            var rate = await basalRate.GetBasalRateAsync(mills);
            answers["profile"] = new JsonObject
            {
                ["key"] = (name ?? "Default") + " basal=" + rate.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                ["detail"] = new JsonObject
                {
                    ["activeProfileName"] = name,
                    ["nameUsedForSchedule"] = name ?? "Default",
                    ["basal"] = rate,
                    ["circadianAdjustment"] = adj is null ? null : new JsonObject
                    {
                        ["percentage"] = adj.Percentage,
                        ["timeshiftMs"] = adj.TimeshiftMs,
                    },
                },
            };
        }
        queries.Add(new JsonObject { ["label"] = (string)q["label"]!, ["t"] = tIso, ["answers"] = answers });
    }

    // Every span the case left behind, including superseded ones.
    var all = await ctx.StateSpans.AsNoTracking().OrderBy(s => s.StartTimestamp).ToListAsync();
    var spanDump = new JsonArray(all.Select(s => (JsonNode)new JsonObject
    {
        ["originalId"] = s.OriginalId,
        ["category"] = s.Category,
        ["state"] = s.State,
        ["start"] = Iso(s.StartTimestamp),
        ["end"] = s.EndTimestamp is null ? null : Iso(s.EndTimestamp.Value),
        ["superseded"] = s.SupersededById is not null,
    }).ToArray());
    var allLinks = await ctx.LinkedRecords.AsNoTracking().ToListAsync();
    var linkDump = new JsonArray(allLinks.Select(l => (JsonNode)new JsonObject
    {
        ["recordType"] = l.RecordType,
        ["recordOriginalId"] = all.FirstOrDefault(s => s.Id == l.RecordId)?.OriginalId,
        ["canonical"] = l.CanonicalId.ToString(),
        ["isPrimary"] = l.IsPrimary,
    }).ToArray());

    return new JsonObject
    {
        ["id"] = (string)c["id"]!,
        ["role"] = (string)c["role"]!,
        ["of"] = c["of"] is null ? null : (string)c["of"]!,
        ["writes"] = writes,
        ["spans"] = spanDump,
        ["dedupLinks"] = linkDump,
        ["queries"] = queries,
    };
}

// "Active at t" two ways: the repository's GetActiveAtAsync with state:null (the call
// SensorContextEnricher makes for overrides) and with the category's active state; plus
// every span GetStateSpansAsync returns for [t, t] (that path applies dedup visibility).
static async Task<JsonObject> SpanAnswer(StateSpanRepository repo, StateSpanService svc,
    StateSpanCategory category, DateTime at, string? activeState)
{
    var any = await repo.GetActiveAtAsync(category, null, at);
    var activeOnly = activeState is null ? any : await repo.GetActiveAtAsync(category, activeState, at);
    var covering = (await svc.GetStateSpansAsync(category: category, from: at, to: at, count: 100))
        .Where(s => s.StartTimestamp <= at && (s.EndTimestamp is null || s.EndTimestamp > at))
        .ToList();

    // key: the span GetActiveAtAsync(state:null) returns; a Cancelled span reads as no target.
    var key = any is null ? "none" : any.State == "Cancelled" ? "none" : any.OriginalId ?? "?";
    return new JsonObject
    {
        ["key"] = key,
        ["keyActiveState"] = activeOnly?.OriginalId ?? "none",
        ["keySet"] = covering.Count == 0 ? "none" : string.Join("+", covering.Select(s => s.OriginalId).OrderBy(x => x, StringComparer.Ordinal)),
        ["detail"] = new JsonObject
        {
            ["getActiveAt_anyState"] = SpanJson(any),
            ["getActiveAt_activeState"] = SpanJson(activeOnly),
            ["covering"] = new JsonArray(covering.Select(s => (JsonNode)SpanJson(s)!).ToArray()),
        },
    };
}

static JsonObject? SpanJson(StateSpan? s) => s is null ? null : new JsonObject
{
    ["originalId"] = s.OriginalId,
    ["state"] = s.State,
    ["start"] = Iso(s.StartTimestamp),
    ["end"] = s.EndTimestamp is null ? null : Iso(s.EndTimestamp.Value),
};

static string Iso(DateTime d) => DateTime.SpecifyKind(d, DateTimeKind.Utc).ToString("yyyy-MM-ddTHH:mm:ss.fffZ");

static object Construct(Assembly asm, string typeName, params object[] leadingArgs)
{
    var type = asm.GetType(typeName, throwOnError: true)!;
    var logger = typeof(NullLogger<>).MakeGenericType(type).GetField("Instance")!.GetValue(null)!;
    var ctorArgs = leadingArgs.Append(logger).ToArray();
    return Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
        null, ctorArgs, null)!;
}

internal readonly record struct V4DecompositionCount(int Created, int Updated, List<string> Types);
