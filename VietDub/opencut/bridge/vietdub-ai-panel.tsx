"use client";

/**
 * (VietDub) Tab "VietDub AI" trong OpenCut: công cụ AI chạy trên máy qua VietDub.
 * - Đọc chữ thành giọng (Ngọc Huyền...) - Phụ đề Việt tự động - Thuyết minh tiếng Việt
 * - Tách nhạc nền & giọng - Xóa phụ đề cứng - Tải video từ link - Dịch chữ đang chọn
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { PanelView } from "@/components/editor/panels/assets/views/base-panel";
import { Button } from "@/components/ui/button";
import { useEditor } from "@/editor/use-editor";
import { mediaTimeToSeconds } from "@/wasm";
import { importVietDubItems, VD_HEADERS, type VietDubItem } from "./import";

type Job = { state: string; progress: number; message: string; error?: string; result?: any };
type Voice = { id: string; label: string };

async function api(path: string, body?: unknown): Promise<any> {
	const res = await fetch(path, {
		method: body === undefined ? "GET" : "POST",
		headers: { ...VD_HEADERS, "Content-Type": "application/json" },
		body: body === undefined ? undefined : JSON.stringify(body),
		cache: "no-store",
	});
	const data = await res.json().catch(() => ({}));
	if (!res.ok) throw new Error(data.error || `Lỗi ${res.status}`);
	return data;
}

async function upload(file: File): Promise<string> {
	const res = await fetch(`/vietdub/upload?name=${encodeURIComponent(file.name)}`, {
		method: "POST",
		headers: VD_HEADERS,
		body: file,
	});
	const data = await res.json().catch(() => ({}));
	if (!res.ok) throw new Error(data.error || "Không gửi được file");
	return data.upload;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
	return (
		<div className="space-y-2 rounded-md border p-3">
			<div className="text-sm font-medium">{title}</div>
			{hint && <div className="text-muted-foreground text-xs">{hint}</div>}
			{children}
		</div>
	);
}

export function VietDubAIView() {
	const editor = useEditor();
	const project = useEditor((e) => e.project.getActiveOrNull());
	const assets = useEditor((e) => e.media.getAssets());
	const [online, setOnline] = useState<boolean | null>(null);
	const [job, setJob] = useState<(Job & { id: string; title: string }) | null>(null);
	const [voices, setVoices] = useState<Record<string, Voice[]>>({});
	const [engine, setEngine] = useState("vieneu");
	const [voice, setVoice] = useState("");
	const [text, setText] = useState("");
	const [url, setUrl] = useState("");
	const [mediaId, setMediaId] = useState("");
	const timer = useRef<ReturnType<typeof setInterval> | null>(null);

	const media = assets.filter((a) => a.type === "video" || a.type === "audio");
	const selectedMedia = media.find((a) => a.id === mediaId) ?? media[0];

	useEffect(() => {
		(async () => {
			try {
				const { job: id } = await api("/vietdub/api/run/voices", {});
				for (let i = 0; i < 40; i++) {
					const s: Job = await api(`/vietdub/api/job/${id}`);
					if (s.state === "done") {
						setVoices(s.result.voices || {});
						setEngine(s.result.default?.engine || "vieneu");
						setVoice(s.result.default?.voice || "");
						break;
					}
					if (s.state === "error") break;
					await new Promise((r) => setTimeout(r, 300));
				}
				setOnline(true);
			} catch {
				setOnline(false);
			}
		})();
		return () => {
			if (timer.current) clearInterval(timer.current);
		};
	}, []);

	const run = useCallback(
		async (title: string, tool: string, args: Record<string, unknown>, onDone: (r: any) => Promise<void>) => {
			if (job && job.state === "running") {
				toast.info("Đang làm việc khác - đợi xong hoặc bấm Hủy.");
				return;
			}
			try {
				setJob({ id: "", title, state: "running", progress: 0, message: "Đang bắt đầu..." });
				const { job: id } = await api(`/vietdub/api/run/${tool}`, args);
				await new Promise<void>((resolve) => {
					timer.current = setInterval(async () => {
						try {
							const s: Job = await api(`/vietdub/api/job/${id}`);
							setJob({ ...s, id, title });
							if (s.state !== "running") {
								if (timer.current) clearInterval(timer.current);
								if (s.state === "done") {
									await onDone(s.result);
									toast.success(`${title}: xong`);
								} else if (s.state === "error") {
									toast.error(`${title} lỗi`, { description: s.error });
								}
								resolve();
							}
						} catch (e) {
							if (timer.current) clearInterval(timer.current);
							toast.error("Mất kết nối với VietDub", { description: String(e) });
							setJob(null);
							resolve();
						}
					}, 700);
				});
			} catch (e) {
				toast.error(`${title} lỗi`, { description: e instanceof Error ? e.message : String(e) });
				setJob(null);
			}
		},
		[job],
	);

	const playhead = () => mediaTimeToSeconds({ time: editor.playback.getCurrentTime() });

	const placeOf = (assetId: string): number => {
		const tracks = editor.timeline.getPreviewTracks?.() as any;
		const all: any[] = tracks ? [...(tracks.main ? [tracks.main] : []), ...(tracks.overlay ?? []), ...(tracks.audio ?? [])] : [];
		for (const t of all) {
			for (const el of t?.elements ?? []) {
				if (el.mediaId === assetId) {
					return mediaTimeToSeconds({ time: el.startTime }) - mediaTimeToSeconds({ time: el.trimStart });
				}
			}
		}
		return 0;
	};

	const importItems = async (items: VietDubItem[], startSeconds: number) => {
		if (!project) return;
		await importVietDubItems({ editor, projectId: project.metadata.id, items, startSeconds });
	};

	const runOnMedia = async (title: string, tool: string) => {
		if (!selectedMedia) {
			toast.info("Chưa có video / âm thanh trong dự án - nhập file trước.");
			return;
		}
		try {
			setJob({ id: "", title, state: "running", progress: 0, message: "Gửi file cho VietDub..." });
			const up = await upload(selectedMedia.file);
			setJob(null);
			const start = placeOf(selectedMedia.id);
			await run(title, tool, { upload: up }, (r) => importItems(r.items || [], tool === "remove_subs" ? playhead() : start));
		} catch (e) {
			setJob(null);
			toast.error(`${title} lỗi`, { description: e instanceof Error ? e.message : String(e) });
		}
	};

	const translateSelected = async () => {
		const refs = editor.selection.getSelectedElements();
		const picked = editor.timeline
			.getElementsWithTracks({ elements: refs })
			.filter(({ element }) => element.type === "text");
		if (!picked.length) {
			toast.info("Chọn 1 hoặc nhiều đoạn chữ trên dòng thời gian trước.");
			return;
		}
		const texts = picked.map(({ element }) => String(element.params.content ?? ""));
		await run("Dịch chữ sang tiếng Việt", "translate_text", { texts }, async (r) => {
			editor.timeline.updateElements({
				updates: picked.map(({ track, element }, i) => ({
					trackId: track.id,
					elementId: element.id,
					patch: { params: { ...element.params, content: r.texts?.[i] ?? texts[i] } },
				})),
			});
		});
	};

	const busy = job?.state === "running";
	const voiceList = voices[engine] ?? [];

	if (online === false) {
		return (
			<PanelView title="VietDub AI">
				<div className="text-muted-foreground p-2 text-sm">
					Không kết nối được VietDub. Hãy mở OpenCut bằng nút "🎬 Dựng tiếp trong OpenCut" trong VietDub và giữ
					VietDub đang mở.
				</div>
			</PanelView>
		);
	}

	return (
		<PanelView title="VietDub AI">
			<div className="space-y-3 pb-4">
				{job && (
					<div className="bg-accent space-y-1 rounded-md p-3 text-xs">
						<div className="font-medium">{job.title}</div>
						<div className="bg-background h-1.5 overflow-hidden rounded">
							<div className="bg-primary h-full transition-all" style={{ width: `${Math.round(job.progress * 100)}%` }} />
						</div>
						<div className="text-muted-foreground">
							{job.state === "error" ? `Lỗi: ${job.error}` : job.message}
						</div>
						{busy && job.id && (
							<Button size="sm" variant="outline" onClick={() => api(`/vietdub/api/cancel/${job.id}`, {})}>
								Hủy
							</Button>
						)}
					</div>
				)}

				<Section title="🎙️ Đọc chữ thành giọng" hint="Giọng AI tiếng Việt, thêm vào dòng thời gian tại đầu phát.">
					<textarea
						className="bg-background w-full rounded-md border p-2 text-sm"
						rows={3}
						placeholder="Nhập lời cần đọc..."
						value={text}
						onChange={(e) => setText(e.target.value)}
					/>
					<div className="flex gap-2">
						<select className="bg-background flex-1 rounded-md border p-1 text-xs" value={engine}
							onChange={(e) => { setEngine(e.target.value); setVoice(""); }}>
							<option value="vieneu">VieNeu (trên máy)</option>
							<option value="edge">Edge (cần mạng)</option>
							<option value="piper">Piper (trên máy)</option>
						</select>
						<select className="bg-background flex-1 rounded-md border p-1 text-xs" value={voice}
							onChange={(e) => setVoice(e.target.value)}>
							<option value="">Giọng mặc định</option>
							{voiceList.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
						</select>
					</div>
					<Button size="sm" className="w-full" disabled={busy || !text.trim()}
						onClick={() => run("Đọc chữ thành giọng", "tts", { text, engine, voice }, (r) => importItems(r.items || [], playhead()))}>
						Tạo giọng & thêm vào dòng thời gian
					</Button>
				</Section>

				<Section title="🎬 Cho video / âm thanh trong dự án" hint="Chọn file, rồi chọn việc cần làm. Kết quả tự thêm vào dòng thời gian, khớp đúng vị trí file.">
					<select className="bg-background w-full rounded-md border p-1 text-xs" value={selectedMedia?.id ?? ""}
						onChange={(e) => setMediaId(e.target.value)}>
						{media.length === 0 && <option value="">(chưa có file - bấm Nhập ở tab Phương tiện)</option>}
						{media.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
					</select>
					<div className="grid grid-cols-1 gap-1.5">
						<Button size="sm" variant="outline" disabled={busy || !selectedMedia} onClick={() => runOnMedia("Phụ đề Việt tự động", "subtitles")}>
							💬 Tạo phụ đề tiếng Việt
						</Button>
						<Button size="sm" variant="outline" disabled={busy || !selectedMedia} onClick={() => runOnMedia("Thuyết minh tiếng Việt", "dub")}>
							🎙️ Thuyết minh tiếng Việt (giọng + phụ đề)
						</Button>
						<Button size="sm" variant="outline" disabled={busy || !selectedMedia} onClick={() => runOnMedia("Tách nhạc nền & giọng", "separate")}>
							🎵 Tách nhạc nền & giọng nói
						</Button>
						<Button size="sm" variant="outline" disabled={busy || !selectedMedia || selectedMedia.type !== "video"} onClick={() => runOnMedia("Xóa phụ đề cứng", "remove_subs")}>
							🧽 Xóa phụ đề cứng (thông minh)
						</Button>
					</div>
				</Section>

				<Section title="🌐 Dịch chữ đang chọn" hint="Chọn các đoạn chữ trên dòng thời gian rồi bấm để dịch sang tiếng Việt.">
					<Button size="sm" variant="outline" className="w-full" disabled={busy} onClick={translateSelected}>
						Dịch sang tiếng Việt
					</Button>
				</Section>

				<Section title="⬇ Tải video từ link" hint="YouTube, TikTok, Douyin, Bilibili, Facebook...">
					<input className="bg-background w-full rounded-md border p-1.5 text-xs" placeholder="https://..."
						value={url} onChange={(e) => setUrl(e.target.value)} />
					<Button size="sm" variant="outline" className="w-full" disabled={busy || !url.trim()}
						onClick={() => run("Tải video từ link", "download", { url }, (r) => importItems(r.items || [], playhead()))}>
						Tải & thêm vào dự án
					</Button>
				</Section>
			</div>
		</PanelView>
	);
}
