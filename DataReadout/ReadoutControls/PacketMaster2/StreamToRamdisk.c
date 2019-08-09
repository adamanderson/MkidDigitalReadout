#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <stdint.h>
#include <sys/time.h>
#include <signal.h>
#include <time.h>
#include <errno.h>
#include <pthread.h>
#include <semaphore.h>
#include <signal.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <inttypes.h>
#include <math.h>
#include <byteswap.h>

#define _POSIX_C_SOURCE 200809L

#define BUFLEN 1500
#define PORT 50000
#define REPORTSTRIDE 100000
#define NRETAIN 1200

// compile with gcc -o StreamToRamdisk StreamToRamdisk.c

/*
  After reboot, create /mnt/ramdisk with this:
  $ sudo mkdir /mnt/ramdisk
  $ sudo mount -t tmpfs -o size=2048M tmpfs /mnt/ramdisk
  $ sudo chmod 0777 /mnt/ramdisk
 */


struct hdrpacket {
    unsigned long timestamp:36;
    unsigned int frame:12;
    unsigned int roach:8;
    unsigned int start:8;
}__attribute__((packed));;

void diep(char *s)
{
  printf("errono: %d",errno); fflush(stdout);
  perror(s);
  exit(1);
}

int need_to_stop() //Checks for a stop file and returns true if found, else returns 0
{
    char stopfilename[] = "stop.bin";
    FILE* stopfile;
    stopfile = fopen(stopfilename,"r");
    if (stopfile == 0) //Don't stop
    {
        errno = 0;
        return 0;
    }
    else //Stop file exists, stop
    {
        printf("found stop file. Exiting\n");
        return 1;
    }
}


void Reader()
{
  char memFileName[1024];
  char memFileNameWriting[1024];
  //set up a socket connection
  struct sockaddr_in si_me;
  int s;
  unsigned char buf[BUFLEN];
  ssize_t nBytesReceived = 0;
  ssize_t nTotalBytes = 0;
  uint64_t swp,swp1;
  struct hdrpacket *hdr;
  uint16_t curframe;
  uint16_t preframe;
  int badDelta = 0;
  uint nBadDelta = 0;
  int tPrevious = -1;
  int tNow;
  int tZero;
  FILE *file_ptr;



  /* set file permissions*/

  char mode[] = "0666";
  int iMode;
  iMode = strtol(mode, 0, 0);

  // Start from scratch
  system("find /mnt/ramdisk/ -name 'frame*' -delete");
 
  printf("StreamToRamdisk: Connecting to Socket!\n");  fflush(stdout);
  if ((s=socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP))==-1)
    diep("socket");
  printf("StreamToRamdisk: socket created\n");
  fflush(stdout);

  memset((char *) &si_me, 0, sizeof(si_me));
  si_me.sin_family = AF_INET;
  si_me.sin_port = htons(PORT);
  si_me.sin_addr.s_addr = htonl(INADDR_ANY);
  if (bind(s, (const struct sockaddr *)(&si_me), sizeof(si_me))==-1)
      diep("bind");
  printf("StreamToRamdisk: socket bind\n");
  fflush(stdout);

  //Set receive buffer size, the default is too small.  
  //If the system will not allow this size buffer, you will need
  //to use sysctl to change the max buffer size
  int retval = 0;
  int bufferSize = 33554432;
  retval = setsockopt(s, SOL_SOCKET, SO_RCVBUF, &bufferSize, sizeof(bufferSize));
  if (retval == -1)
    diep("set receive buffer size");

  //Set recv to timeout after 3 secs
  const struct timeval sock_timeout={.tv_sec=3, .tv_usec=0};
  retval = setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (char*)&sock_timeout, sizeof(sock_timeout));
  if (retval == -1)
    diep("set receive buffer size");

  uint64_t nFrames = 0;
  
  printf("begin:  reportStride = %d\n",REPORTSTRIDE);
  printf("begin:       nRetain = %d\n",NRETAIN);
  
  while (access( "/mnt/ramdisk/QUIT", F_OK ) == -1)
  {
    tNow = (int)time(NULL);
    nBytesReceived = recv(s, buf, BUFLEN, 0);
    if (nBytesReceived == -1)
    {
      if (errno == EAGAIN || errno == EWOULDBLOCK)
      {// recv timed out, clear the error and check again
        errno = 0;
        continue;
      }
      else
        diep("recvfrom()");
    }
    swp = *((uint64_t *) (&buf[0]));
    swp1 = __bswap_64(swp);
    hdr = (struct hdrpacket *) (&swp1);             
    curframe = hdr->frame;
    if (nFrames > 0) {
      if ((curframe == preframe+1) || (curframe == 0 && preframe == 4095)) {
	badDelta = 0;
      } else {
	badDelta = 1;
      }
    } else {
      badDelta = 0;
    }
    nBadDelta += badDelta;
    if ((nFrames%REPORTSTRIDE == 0) || (nFrames < 10)) {
      printf("StreamToRamdisk:  curframe=%4d nFrames=%10ld  nBadDelta=%d\n",curframe,nFrames,nBadDelta);
      fflush(stdout);
    }
    preframe = curframe;

    if (tNow != tPrevious) {
      if (tPrevious == -1) {
	// First file, nothing to close, rename, or remove
	tZero = tNow;
      } else {
	// Close the previous file, rename it, and remove old ones
	fclose(file_ptr);
	sprintf(memFileName,"/mnt/ramdisk/frames%010d.bin", tPrevious);
	rename(memFileNameWriting, memFileName);
	if (tNow-tZero >= NRETAIN) {
	  sprintf(memFileName,"/mnt/ramdisk/frames%010d.bin", tNow-NRETAIN);
	  //printf("now remove %s\n",memFileName);
	  remove(memFileName);
	}
      }
      // Get ready to write
      sprintf(memFileNameWriting,
	      "/mnt/ramdisk/frames%010d.binWRITING", tNow);
      file_ptr = fopen(memFileNameWriting,"wb");
      if (fchmod(fileno(file_ptr), iMode) < 0 ) {
	fprintf(stderr, "StreamToRamdisk: error in fchmod %s\n", memFileNameWriting);
      }

	     
    }
    fwrite((const void*) &nBytesReceived, sizeof(ssize_t), 1, file_ptr);
    //if (tNow==tZero) {
    //  printf("nFrames=%4lu nBytesReceived=%ld  sizeof(ssize_t)=%lu\n",nFrames,nBytesReceived,sizeof(ssize_t));
    //}
    fwrite(buf, 1, nBytesReceived, file_ptr);
    tPrevious = tNow;
    nTotalBytes += nBytesReceived;
    ++nFrames;
  }
  if (tPrevious == -1) {
    printf("no files written\n");
  } else{
    fclose(file_ptr);
    sprintf(memFileName,"/mnt/ramdisk/frames%010d.bin", tPrevious);
    rename(memFileNameWriting, memFileName);
    printf("last file written:  %s\n",memFileName);
  }
  remove("/mnt/ramdisk/QUIT");
  printf("received %ld frames, %ld bytes\n",nFrames,nTotalBytes);
  close(s);
  return;
}

int main(void)
{
    signal(SIGCHLD, SIG_IGN);  /* now I don't have to wait()! */
    Reader();
}
