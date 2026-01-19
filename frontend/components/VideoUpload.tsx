"use client";

/**
 * Video upload component
 * Handles video file upload with drag-and-drop support
 */

import { useState, useRef } from "react";
import { uploadVideo } from "@/lib/api";
import { useRouter } from "next/navigation";
import { Camera } from "lucide-react";

export default function VideoUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [odometerImage, setOdometerImage] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [odometerDragActive, setOdometerDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const odometerInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  /**
   * Handle file selection
   */
  const handleFileSelect = (selectedFile: File) => {
    // Validate file type
    if (!selectedFile.type.startsWith("video/")) {
      setError("Please select a valid video file");
      return;
    }

    // Validate file size (500MB limit)
    if (selectedFile.size > 500 * 1024 * 1024) {
      setError("File size must be less than 500MB");
      return;
    }

    setFile(selectedFile);
    setError(null);
  };

  /**
   * Handle odometer image selection
   */
  const handleOdometerImageSelect = (selectedFile: File) => {
    // Validate file type
    if (!selectedFile.type.startsWith("image/")) {
      setError("Please select a valid image file");
      return;
    }

    // Validate file size (10MB limit)
    if (selectedFile.size > 10 * 1024 * 1024) {
      setError("Image size must be less than 10MB");
      return;
    }

    setOdometerImage(selectedFile);
    setError(null);
  };

  /**
   * Handle file input change
   */
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  /**
   * Handle drag and drop
   */
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  /**
   * Handle file drop
   */
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  /**
   * Handle upload
   */
  const handleUpload = async () => {
    if (!file) {
      setError("Please select a video file first");
      return;
    }

    setUploading(true);
    setError(null);
    setUploadProgress(0);

    try {
      const result = await uploadVideo(file, odometerImage, (progress) => {
        setUploadProgress(progress);
      });

      // Redirect to job status page
      router.push(`/job/${result.jobId}`);
    } catch (err: any) {
      setError(err.response?.data?.message || "Upload failed. Please try again.");
      setUploading(false);
    }
  };

  /**
   * Handle odometer image drag and drop
   */
  const handleOdometerDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setOdometerDragActive(true);
    } else if (e.type === "dragleave") {
      setOdometerDragActive(false);
    }
  };

  const handleOdometerDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setOdometerDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleOdometerImageSelect(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h2 className="text-2xl font-bold mb-6 text-slate-900">Upload Vehicle Video</h2>

      {/* Odometer Image Upload */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          Odometer Photo <span className="text-slate-500 font-normal">(Optional - improves accuracy)</span>
        </label>
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-all bg-white ${
            odometerDragActive
              ? "border-green-500 bg-green-50"
              : "border-slate-300 hover:border-green-400"
          }`}
          onDragEnter={handleOdometerDrag}
          onDragLeave={handleOdometerDrag}
          onDragOver={handleOdometerDrag}
          onDrop={handleOdometerDrop}
        >
          <input
            ref={odometerInputRef}
            type="file"
            accept="image/*"
            onChange={(e) => {
              if (e.target.files && e.target.files[0]) {
                handleOdometerImageSelect(e.target.files[0]);
              }
            }}
            className="hidden"
          />

          {!odometerImage ? (
            <>
              <Camera className="mx-auto h-10 w-10 text-green-500 mb-2" />
              <p className="text-sm text-slate-700 font-medium">
                Drag and drop an odometer photo here, or
              </p>
              <button
                onClick={() => odometerInputRef.current?.click()}
                className="mt-2 bg-green-600 text-white hover:bg-green-700 px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors"
              >
                browse image
              </button>
              <p className="mt-2 text-xs text-slate-500">
                JPG, PNG, HEIC (Max 10MB)
              </p>
            </>
          ) : (
            <div>
              <p className="text-sm font-medium text-slate-800">{odometerImage.name}</p>
              <p className="text-xs text-slate-600 mt-1">
                {(odometerImage.size / (1024 * 1024)).toFixed(2)} MB
              </p>
              <button
                onClick={() => setOdometerImage(null)}
                className="mt-2 text-xs text-red-600 hover:text-red-700 font-medium"
              >
                Remove image
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Drag and drop area */}
      <div
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-all bg-white ${
          dragActive
            ? "border-blue-500 bg-blue-50"
            : "border-slate-300 hover:border-blue-400"
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          onChange={handleInputChange}
          className="hidden"
        />

        {!file ? (
          <>
            <svg
              className="mx-auto h-12 w-12 text-blue-500"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p className="mt-4 text-lg text-slate-700 font-medium">
              Drag and drop a video file here, or
            </p>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mt-2 bg-blue-600 text-white hover:bg-blue-700 px-6 py-2 rounded-lg font-medium shadow-sm transition-colors"
            >
              browse files
            </button>
            <p className="mt-2 text-sm text-slate-500">
              Supported formats: MP4, MOV, AVI, MKV (Max 500MB)
            </p>
          </>
        ) : (
          <div>
            <p className="text-lg font-medium text-slate-800">{file.name}</p>
            <p className="text-sm text-slate-600 mt-1">
              {(file.size / (1024 * 1024)).toFixed(2)} MB
            </p>
            <button
              onClick={() => setFile(null)}
              className="mt-4 text-sm text-red-600 hover:text-red-700 font-medium"
            >
              Remove file
            </button>
          </div>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="mt-4 p-4 bg-red-50 border-2 border-red-300 rounded-xl shadow-md">
          <p className="text-red-800 font-medium">{error}</p>
        </div>
      )}

      {/* Upload progress */}
      {uploading && (
        <div className="mt-6 bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <div className="flex justify-between text-sm text-slate-700 mb-2 font-medium">
            <span>Uploading...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-3">
            <div
              className="bg-blue-600 h-3 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Upload button */}
      {file && !uploading && (
        <button
          onClick={handleUpload}
          className="mt-6 w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-blue-700 transition-colors shadow-sm"
        >
          Upload and Process Video
        </button>
      )}
    </div>
  );
}
