import os
import sys
import json
import time
import subprocess
import torch
import logging
import psutil
import threading
import queue
import shutil
import torch.nn as nn
import torch.nn.functional as F
import math
from upcunet_v3 import UpCunet2x, UpCunet3x, UpCunet4x

# Cross-platform subprocess creation flags (hides popping console windows on Windows)
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

def find_executable(name):
    found = shutil.which(name)
    if found:
        return found
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_ext = f"{name}.exe" if sys.platform == 'win32' else name
    local_path = os.path.join(base_dir, "ffmpeg", "bin", local_ext)
    if os.path.exists(local_path):
        return local_path
    return name




# ============================================================================
# GENERIC ESRGAN / REAL-ESRGAN RRDB NET
# ============================================================================

class ResidualDenseBlock_5C(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf, gc=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock_5C(nf, gc)
        self.rdb2 = ResidualDenseBlock_5C(nf, gc)
        self.rdb3 = ResidualDenseBlock_5C(nf, gc)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, in_nc=3, out_nc=3, nf=64, nb=23, gc=32, scale=4):
        super().__init__()
        self.scale = scale
        self.conv_first = nn.Conv2d(in_nc, nf, 3, 1, 1)
        self.RRDB_trunk = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        self.trunk_conv = nn.Conv2d(nf, nf, 3, 1, 1)
        # Upsampling
        self.upconv1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.upconv2 = nn.Conv2d(nf, nf, 3, 1, 1)
        if scale == 8:
            self.upconv3 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.hr_conv = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, out_nc, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        fea = self.conv_first(x)
        trunk = self.trunk_conv(self.RRDB_trunk(fea))
        fea = fea + trunk

        fea = self.lrelu(self.upconv1(F.interpolate(fea, scale_factor=2, mode='nearest')))
        fea = self.lrelu(self.upconv2(F.interpolate(fea, scale_factor=2, mode='nearest')))
        if self.scale == 8:
            fea = self.lrelu(self.upconv3(F.interpolate(fea, scale_factor=2, mode='nearest')))
        
        out = self.conv_last(self.lrelu(self.hr_conv(fea)))
        return out


# ============================================================================
# UNIVERSAL MODEL LOADER & TILE INFERENCE
# ============================================================================

def load_model(model_path, device='cuda', half=True):
    """
    Loads PyTorch .pth model weights and automatically inspects state_dict keys.
    """
    state_dict = torch.load(model_path, map_location='cpu')
    if 'params_ema' in state_dict:
        state_dict = state_dict['params_ema']
    elif 'params' in state_dict:
        state_dict = state_dict['params']
    elif 'model_state_dict' in state_dict:
        state_dict = state_dict['model_state_dict']

    scale = 2
    
    # Check if Pro model
    pro = "pro" in state_dict
    if pro:
        del state_dict["pro"]
        
    is_cugan = False
    if any('unet1' in k for k in state_dict.keys()):
        is_cugan = True
        # It's RealCUGAN
        if 'up3x' in model_path or 'up3x' in list(state_dict.keys())[0]:
            scale = 3
            model = UpCunet3x()
        elif 'up4x' in model_path or 'up4x' in list(state_dict.keys())[0]:
            scale = 4
            model = UpCunet4x()
        else:
            scale = 2
            model = UpCunet2x()
            
        model.pro = pro
    else:
        # RRDB / Real-ESRGAN
        if any('upconv1' in k for k in state_dict.keys()):
            if 'upconv3.weight' in state_dict:
                scale = 8
            elif 'upconv2.weight' in state_dict:
                scale = 4
            else:
                scale = 2
            model = RRDBNet(scale=scale)

    try:
        model.load_state_dict(state_dict, strict=True if is_cugan else False)
    except Exception as e:
        print(f"[Model Loader Warning] Load fallback: {e}")

    model.eval()
    model.to(device)
    if half and device.startswith('cuda'):
        model.half()
    
    return model, scale


def upscale_tensor_tiled(model, input_tensor, scale, tile_size=512, tile_pad=10, device='cuda', half=True):
    """
    Upscales a single frame BxCxHxW tensor with seamless tile overlap stitching to avoid VRAM OOM.
    ponytail: tile-based grid iteration -> upgrade path: add CUDA stream parallelism if required
    """
    def _forward_pass(m, x):
        if hasattr(m, 'pro'):
            if m.pro:
                x = x * 0.7 + 0.15
            out = m(x, 0, 0, 1.0, m.pro)
            return out.float() / 255.0
        return m(x)

    if tile_size == 0:
        with torch.inference_mode():
            return _forward_pass(model, input_tensor)

    b, c, h, w = input_tensor.shape
    out_h, out_w = h * scale, w * scale
    output_tensor = torch.zeros((b, c, out_h, out_w), device=device, dtype=torch.float16 if half else torch.float32)

    tiles_x = math.ceil(w / tile_size)
    tiles_y = math.ceil(h / tile_size)

    with torch.inference_mode():
        for y in range(tiles_y):
            for x in range(tiles_x):
                x_start = x * tile_size
                x_end = min(x_start + tile_size, w)
                y_start = y * tile_size
                y_end = min(y_start + tile_size, h)

                in_x_start = max(x_start - tile_pad, 0)
                in_x_end = min(x_end + tile_pad, w)
                in_y_start = max(y_start - tile_pad, 0)
                in_y_end = min(y_end + tile_pad, h)

                tile_in = input_tensor[:, :, in_y_start:in_y_end, in_x_start:in_x_end]

                tile_out = _forward_pass(model, tile_in)

                out_x_start = (x_start - in_x_start) * scale
                out_x_end = out_x_start + (x_end - x_start) * scale
                out_y_start = (y_start - in_y_start) * scale
                out_y_end = out_y_start + (y_end - y_start) * scale

                target_x_start = x_start * scale
                target_x_end = x_end * scale
                target_y_start = y_start * scale
                target_y_end = y_end * scale

                output_tensor[:, :, target_y_start:target_y_end, target_x_start:target_x_end] = \
                    tile_out[:, :, out_y_start:out_y_end, out_x_start:out_x_end]

    return output_tensor


# ============================================================================
# VIDEO PROBE & ENCODER DETECTION UTILITIES
# ============================================================================

def probe_video(input_path):
    """
    Probes video metadata using ffprobe JSON output.
    Returns: dict(width, height, fps, total_frames, duration, audio_tracks, subtitle_tracks)
    """
    ffprobe_bin = find_executable('ffprobe')
    cmd = [
        ffprobe_bin, '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', input_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, creationflags=SUBPROCESS_FLAGS)
        data = json.loads(res.stdout)
    except Exception as e:
        raise RuntimeError(f"FFprobe failed to read {input_path}: {e}")

    width, height, fps, total_frames, duration = 0, 0, 24.0, 0, 0.0
    audio_tracks, subtitle_tracks = 0, 0

    for stream in data.get('streams', []):
        codec_type = stream.get('codec_type')
        if codec_type == 'video' and width == 0:
            width = int(stream.get('width', 0))
            height = int(stream.get('height', 0))
            # Calculate FPS
            r_fps = stream.get('r_frame_rate', '24/1')
            if '/' in r_fps:
                num, den = r_fps.split('/')
                fps = float(num) / float(den) if float(den) > 0 else 24.0
            else:
                fps = float(r_fps)
            
            # Total frames
            if 'nb_frames' in stream:
                total_frames = int(stream['nb_frames'])
        elif codec_type == 'audio':
            audio_tracks += 1
        elif codec_type == 'subtitle':
            subtitle_tracks += 1

    # Duration fallback
    if 'format' in data and 'duration' in data['format']:
        duration = float(data['format']['duration'])
        if total_frames == 0 and duration > 0:
            total_frames = int(duration * fps)

    return {
        'width': width,
        'height': height,
        'fps': fps,
        'total_frames': total_frames,
        'duration': duration,
        'audio_tracks': audio_tracks,
        'subtitle_tracks': subtitle_tracks
    }


def probe_system_encoders():
    """
    Probes system ffmpeg for supported NVENC and CPU encoders.
    """
    ffmpeg_bin = find_executable('ffmpeg')
    cmd = [ffmpeg_bin, '-encoders']
    encoders = []
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=SUBPROCESS_FLAGS)
        out = res.stdout
        all_possible = [
            ('hevc_nvenc', 'NVIDIA NVENC H.265 / HEVC'),
            ('h264_nvenc', 'NVIDIA NVENC H.264 / AVC'),
            ('av1_nvenc', 'NVIDIA NVENC AV1'),
            ('libx264', 'CPU Software H.264 (libx264)'),
            ('libx265', 'CPU Software H.265 (libx265)'),
            ('libvpx-vp9', 'CPU Software VP9 (libvpx-vp9)')
        ]
        for enc_id, label in all_possible:
            if enc_id in out:
                encoders.append((enc_id, label))
    except Exception:
        encoders = [('libx264', 'CPU Software H.264 (libx264)')]
    
    return encoders


# ============================================================================
# DUAL-FFMPEG ASYNC DOUBLE-BUFFERED PIPELINE
# ============================================================================

def get_auto_crop(input_path):
    import re
    ffmpeg_bin = find_executable('ffmpeg')
    cmd = [
        ffmpeg_bin, '-i', input_path, '-t', '2',
        '-vf', 'cropdetect=24:16:0', '-f', 'null', '-'
    ]
    try:
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, creationflags=SUBPROCESS_FLAGS)
        matches = re.findall(r'crop=([0-9:]+)', res.stderr)
        if matches:
            return matches[-1]
    except Exception as e:
        logging.warning(f"Auto-crop detection failed: {e}")
    return None

def run_upscale_pipeline(
    input_path,
    output_path,
    model_path,
    custom_scale=None,
    target_fps=None,
    encoder='hevc_nvenc',
    audio_mode=0,
    crf=20,
    grain=0,
    saturation=1.0,
    auto_crop=False,
    tile_size=512,
    half=True,
    sample_test=False,
    target_res=None,
    res_method='lanczos',
    progress_cb=None,
    cancel_event=None
):
    """
    Executes dual-FFmpeg piping with PyTorch CUDA frame processing.
    """
    class AsyncWriter(threading.Thread):
        def __init__(self, pipe):
            super().__init__()
            self.pipe = pipe
            self.q = queue.Queue(maxsize=2)
            self.daemon = True
            self.error = None
        def run(self):
            while True:
                item = self.q.get()
                if item is None: break
                try:
                    self.pipe.write(item)
                except Exception as e:
                    self.error = e
                    self.q.task_done()
                    break
                self.q.task_done()
        def put(self, item):
            while True:
                if not self.is_alive():
                    raise RuntimeError(f"AsyncWriter thread died: {self.error}")
                try:
                    self.q.put(item, timeout=0.5)
                    break
                except queue.Full:
                    continue
        def stop(self):
            if self.is_alive():
                self.q.put(None)
                self.join()
    video_info = probe_video(input_path)
    in_w, in_h = video_info['width'], video_info['height']
    src_fps = video_info['fps']
    total_frames = video_info['total_frames']
    out_fps = target_fps if target_fps and target_fps > 0 else src_fps

    crop_filter = None
    if auto_crop:
        if progress_cb: progress_cb({'status_override': 'Detecting black bars for auto-crop...'})
        crop_filter = get_auto_crop(input_path)
        if crop_filter:
            logging.info(f"Auto-crop detected: {crop_filter}")
            cw, ch, cx, cy = map(int, crop_filter.split(':'))
            in_w, in_h = cw, ch

    logging.info(f"Engine Starting. Input: {in_w}x{in_h} @ {src_fps}fps. Target output FPS: {out_fps}")

    if in_w == 0 or in_h == 0:
        raise ValueError(f"Invalid input video dimensions for {input_path}")

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logging.debug(f"Loading model {model_path} on {device} (half={half})")
    model, model_scale = load_model(model_path, device=device, half=half)

    # 1. cuDNN Benchmark
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True
        logging.debug("cuDNN Benchmark autotuning enabled.")

    # 2. PyTorch 2.0 Graph Compilation
    if hasattr(torch, 'compile') and device.startswith('cuda'):
        try:
            if progress_cb: progress_cb({'status_override': 'Compiling GPU Kernel (Takes 1-2m on first run)...'})
            logging.info("Attempting torch.compile kernel fusion...")
            model = torch.compile(model, mode='reduce-overhead')
            if progress_cb: progress_cb({'status_override': 'Kernel Compiled!'})
        except Exception as e:
            logging.warning(f"torch.compile skipped (fallback to standard): {e}")

    scale_factor = custom_scale if custom_scale and custom_scale > 0 else model_scale
    out_w, out_h = int(in_w * scale_factor), int(in_h * scale_factor)
    logging.debug(f"Scale Factor: {scale_factor}x -> Output Res: {out_w}x{out_h} (before padding)")

    if target_res:
        out_w, out_h = target_res

    # Make dimensions even numbers (required by h264/hevc encoders)
    out_w = out_w if out_w % 2 == 0 else out_w + 1
    out_h = out_h if out_h % 2 == 0 else out_h + 1

    in_frame_bytes = in_w * in_h * 3
    out_frame_bytes = out_w * out_h * 3

    # FFmpeg Decoder Process
    ffmpeg_bin = find_executable('ffmpeg')
    decoder_cmd = [
        ffmpeg_bin, '-hwaccel', 'auto', '-threads', '1'
    ]
    if sample_test:
        decoder_cmd.extend(['-t', '5'])
    
    # Calculate max frames for sample test
    max_frames = int(src_fps * 5) if sample_test else total_frames
    
    decoder_vf = 'scale=out_color_matrix=bt709'
    if crop_filter:
        decoder_vf = f'crop={crop_filter},{decoder_vf}'
        
    decoder_cmd.extend([
        '-i', input_path,
        '-vf', decoder_vf,
        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'
    ])
    decoder_proc = subprocess.Popen(decoder_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**7, creationflags=SUBPROCESS_FLAGS)

    # FFmpeg Encoder & Track Remuxer Process
    encoder_cmd = [
        ffmpeg_bin, '-loglevel', 'error', '-y',
        '-f', 'rawvideo', '-pixel_format', 'rgb24',
        '-video_size', f"{out_w}x{out_h}",
        '-framerate', str(out_fps),
        '-i', 'pipe:0'
    ]
    if not sample_test:
        encoder_cmd.extend([
            '-i', input_path,
            '-map', '0:v:0',
            '-map', '1:a?', '-map', '1:s?', '-map', '1:d?', '-map', '1:t?'
        ])
    
    scale_filter = 'scale=in_color_matrix=bt709,format=yuv420p'
    if saturation != 1.0:
        scale_filter += f',eq=saturation={saturation}'
    if grain > 0:
        scale_filter += f',noise=alls={grain}:allf=t+u'
        
    encoder_cmd.extend([
        '-c:v', encoder,
        '-vf', scale_filter,
        '-colorspace', '1', '-color_primaries', '1', '-color_trc', '1'
    ])

    if 'nvenc' in encoder:
        encoder_cmd.extend(['-preset', 'p5', '-cq', str(crf), '-rc', 'vbr'])
    else:
        encoder_cmd.extend(['-crf', str(crf), '-preset', 'medium'])

    if not sample_test:
        if audio_mode == 1:
            encoder_cmd.extend([
                '-c:a', 'aac', '-b:a', '192k', '-c:s', 'copy', '-c:d', 'copy', '-c:t', 'copy'
            ])
        else:
            encoder_cmd.extend([
                '-c:a', 'copy', '-c:s', 'copy', '-c:d', 'copy', '-c:t', 'copy'
            ])
    
    temp_output = output_path + ".partial"
    if os.path.exists(temp_output):
        try: os.remove(temp_output)
        except: pass

    ext = os.path.splitext(output_path)[1].lower()
    format_map = {'.mkv': 'matroska', '.mp4': 'mp4', '.mov': 'mov', '.avi': 'avi'}
    out_format = format_map.get(ext, 'matroska')

    encoder_cmd.extend([
        '-movflags', '+faststart',
        '-f', out_format,
        temp_output
    ])

    logging.debug(f"Decoder CMD: {' '.join(decoder_cmd)}")
    logging.debug(f"Encoder CMD: {' '.join(encoder_cmd)}")

    # Lazy directory creation
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    encoder_proc = subprocess.Popen(encoder_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**7, creationflags=SUBPROCESS_FLAGS)
    writer = AsyncWriter(encoder_proc.stdin)
    writer.start()

    frame_count = 0
    start_time = time.time()

    pinned_in = torch.empty(in_frame_bytes, dtype=torch.uint8, pin_memory=True)
    numpy_in = pinned_in.numpy()
    
    pinned_out_0 = torch.empty((out_h, out_w, 3), dtype=torch.uint8, pin_memory=True)
    pinned_out_1 = torch.empty((out_h, out_w, 3), dtype=torch.uint8, pin_memory=True)
    pinned_outs = [pinned_out_0, pinned_out_1]
    numpys_out = [pinned_out_0.numpy(), pinned_out_1.numpy()]
    buf_idx = 0

    success = False
    try:
        while True:
            if cancel_event and cancel_event.is_set():
                break

            bytes_read = decoder_proc.stdout.readinto(numpy_in)
            if bytes_read < in_frame_bytes:
                break

            # Zero-copy CPU read -> Fast PCIe transfer
            tensor_in = pinned_in.view(in_h, in_w, 3).to(device, non_blocking=True)
            
            # Fast GPU kernel math
            tensor_in = tensor_in.permute(2, 0, 1).unsqueeze(0)
            if half and device.startswith('cuda'):
                tensor_in = tensor_in.half().div_(255.0)
            else:
                tensor_in = tensor_in.float().div_(255.0)

            # PyTorch CUDA Inference
            with torch.inference_mode():
                tensor_out = upscale_tensor_tiled(
                    model, tensor_in, scale=model_scale,
                    tile_size=tile_size, device=device, half=half
                )
                
                if target_res:
                    res_map = {'lanczos': 'bicubic', 'bicubic': 'bicubic', 'bilinear': 'bilinear', 'neighbor': 'nearest'}
                    py_mode = res_map.get(res_method.lower(), 'bicubic')
                    if py_mode in ['bicubic', 'bilinear']:
                        tensor_out = torch.nn.functional.interpolate(tensor_out, size=(out_h, out_w), mode=py_mode, align_corners=False)
                    else:
                        tensor_out = torch.nn.functional.interpolate(tensor_out, size=(out_h, out_w), mode=py_mode)
                else:
                    _, _, th, tw = tensor_out.shape
                    if th != out_h or tw != out_w:
                        tensor_out = torch.nn.functional.interpolate(
                            tensor_out, size=(out_h, out_w), mode='bilinear', align_corners=False
                        )

                # In-place math, zero-allocation cast, and layout repack
                tensor_out.clamp_(0, 1).mul_(255.0)
                tensor_out = tensor_out.to(torch.uint8).squeeze(0).permute(1, 2, 0).contiguous()
                pinned_outs[buf_idx].copy_(tensor_out, non_blocking=True)
                torch.cuda.synchronize()

            # Output zero-copy bypass via Async Writer Thread
            writer.put(numpys_out[buf_idx])
            buf_idx = 1 - buf_idx
            frame_count += 1
            
            if sample_test and frame_count >= max_frames:
                logging.info("5s sample test frame limit reached. Stopping.")
                break
            
            # Explicitly free memory
            del tensor_in, tensor_out

            # Progress Reporting (Throttled to 4 updates/sec at 24fps to save UI CPU load)
            total_target = max_frames if sample_test else total_frames
            if progress_cb and (frame_count % 6 == 0 or frame_count == total_target):
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                percent = (frame_count / total_target * 100) if total_target > 0 else 0
                eta = ((total_target - frame_count) / fps) if fps > 0 else 0
                progress_cb({
                    'frame': frame_count,
                    'total_frames': total_target,
                    'percent': min(percent, 100.0),
                    'fps': fps,
                    'eta': eta
                })
        
        success = True
            
    except Exception as e:
        logging.error(f"Error in engine pipeline: {e}")
        raise
    finally:
        if 'writer' in locals():
            writer.stop()
        if decoder_proc.poll() is None:
            decoder_proc.kill()
            if decoder_proc.stdout:
                try: decoder_proc.stdout.close()
                except: pass
            decoder_proc.wait()
        if encoder_proc.stdin and not encoder_proc.stdin.closed:
            try: encoder_proc.stdin.close()
            except: pass
        
        _, err = encoder_proc.communicate()
        if encoder_proc.returncode != 0 and err:
            err_out = err.decode('utf-8', errors='ignore')
            if err_out:
                logging.error(f"FFmpeg Encoder Error: {err_out}")

        # Instant zero-overhead rename upon clean 100% completion
        if not (cancel_event and cancel_event.is_set()):
            if os.path.exists(temp_output):
                if os.path.exists(output_path):
                    try: os.remove(output_path)
                    except: pass
                os.rename(temp_output, output_path)
        
        # Explicit VRAM Cleanup
        try:
            del model, pinned_in, pinned_out_0, pinned_out_1
        except Exception:
            pass
            
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        import gc
        gc.collect()

        # Send 100% complete signal if we finished successfully without cancelling
        if progress_cb and success and not (cancel_event and cancel_event.is_set()):
            progress_cb({
                'frame': frame_count,
                'total_frames': total_frames,
                'fps': 0,
                'eta': 0,
                'percent': 100
            })

    return {
        'frames_processed': frame_count,
        'elapsed_time': time.time() - start_time,
        'output_path': output_path
    }
